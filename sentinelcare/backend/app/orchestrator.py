"""Agent Orchestrator — manages multiple detection agents running in parallel."""

from __future__ import annotations

from .agent_base import BaseAgent
from .models import AgentState, AgentStateName, PoseFeatures, Alert
from .event_store import event_store


class AgentOrchestrator:
    """Centralized manager for all detection agents.
    
    Provides a single interface for the vision loop to update all agents
    and collect their states. Handles alert emission when agents transition
    to CRITICAL_ALERT state.
    """

    def __init__(self):
        """Initialize orchestrator with empty agent registry."""
        self._agents: dict[str, BaseAgent] = {}
        self._previous_states: dict[str, AgentStateName] = {}

    def register_agent(self, name: str, agent: BaseAgent) -> None:
        """Register a new agent with the orchestrator.
        
        Args:
            name: Unique identifier for this agent (e.g., "ResponseGuard", "Seizure")
            agent: Agent instance implementing BaseAgent interface
            
        Raises:
            ValueError: If an agent with this name is already registered
        """
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered")
        
        self._agents[name] = agent
        self._previous_states[name] = AgentStateName.NORMAL

    def deregister_agent(self, name: str) -> None:
        """Deregister an agent from the orchestrator.
        
        Args:
            name: Unique identifier for the agent to remove
        """
        if name in self._agents:
            del self._agents[name]
            if name in self._previous_states:
                del self._previous_states[name]

    def update(self, features: PoseFeatures, pose_detected: bool) -> list[AgentState]:
        """Update all registered agents and return their states.
        
        Args:
            features: Extracted pose features for this frame
            pose_detected: Whether a valid pose was detected in this frame
            
        Returns:
            List of AgentState objects, one per registered agent, in registration order
        """
        states = []
        
        for name, agent in self._agents.items():
            try:
                # Update agent and get new state
                state = agent.update(features, pose_detected)
                states.append(state)
                
                # Check for CRITICAL_ALERT transition
                prev_state = self._previous_states.get(name, AgentStateName.NORMAL)
                if state.state == AgentStateName.CRITICAL_ALERT and prev_state != AgentStateName.CRITICAL_ALERT:
                    # First transition to CRITICAL_ALERT - emit alert
                    self._emit_alert(name, state)
                
                # Update previous state
                self._previous_states[name] = state.state
                
            except Exception as e:
                # Log error but continue processing other agents
                import logging
                logging.error(f"Agent '{name}' update failed: {e}", exc_info=True)
                
                # Return last known state or default
                if name in self._previous_states:
                    # Create a default state with the last known state
                    states.append(AgentState(
                        agent_name=name,
                        state=self._previous_states[name],
                        summary=f"Agent error: {str(e)}"
                    ))
                else:
                    # No previous state, return default NORMAL
                    states.append(AgentState(agent_name=name))
        
        return states

    def reset_all(self) -> None:
        """Reset all registered agents to NORMAL state.
        
        Calls reset() on every agent and clears previous state tracking.
        """
        for agent in self._agents.values():
            agent.reset()
        
        # Reset previous state tracking
        for name in self._agents.keys():
            self._previous_states[name] = AgentStateName.NORMAL

    def get_agent(self, name: str) -> BaseAgent | None:
        """Retrieve a specific agent by name.
        
        Args:
            name: Agent identifier
            
        Returns:
            Agent instance if found, None otherwise
        """
        return self._agents.get(name)

    def _emit_alert(self, agent_name: str, state: AgentState) -> None:
        """Emit an alert to the EventStore for a CRITICAL_ALERT transition.
        
        Args:
            agent_name: Name of the agent that triggered the alert
            state: Current agent state with CRITICAL_ALERT status
        """
        from .models import Event

        latest_alert = event_store.get_latest_alert()
        if (
            latest_alert
            and latest_alert.event.agent == agent_name
            and latest_alert.event.status == "critical_alert"
        ):
            return
        
        # Create event from agent state
        event = Event(
            agent=agent_name,
            event_type=state.event_type,
            status="critical_alert",
            confidence=state.confidence,
            summary=state.summary,
            recovery_window_seconds=state.timer_total,
        )
        
        event_store.add_event(event)
        
        # Create and store alert
        alert = Alert(event=event)
        event_store.add_alert(alert)
