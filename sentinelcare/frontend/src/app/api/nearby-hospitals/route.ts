import { NextRequest, NextResponse } from 'next/server';

interface Hospital {
  name: string;
  address: string;
  phone?: string;
  distance: number;
  latitude: number;
  longitude: number;
  rating?: number;
  openNow?: boolean;
}

export async function POST(request: NextRequest) {
  try {
    const { latitude, longitude } = await request.json();

    if (!latitude || !longitude) {
      return NextResponse.json(
        { error: 'Latitude and longitude are required' },
        { status: 400 }
      );
    }

    const apiKey = process.env.GOOGLE_MAPS_API_KEY;

    if (!apiKey) {
      // Return mock data for hackathon demo when no API key is set
      return NextResponse.json({
        hospitals: getMockHospitals(latitude, longitude),
        isMockData: true,
      });
    }

    // Use Google Places API to find nearby hospitals
    const url = `https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=${latitude},${longitude}&radius=10000&type=hospital&key=${apiKey}`;

    const response = await fetch(url);
    const data = await response.json();

    if (data.status !== 'OK' && data.status !== 'ZERO_RESULTS') {
      console.error('Google Places API error:', data.status);
      return NextResponse.json({
        hospitals: getMockHospitals(latitude, longitude),
        isMockData: true,
      });
    }

    const hospitals: Hospital[] = (data.results || []).slice(0, 5).map((place: any) => ({
      name: place.name,
      address: place.vicinity,
      phone: place.formatted_phone_number,
      distance: calculateDistance(
        latitude,
        longitude,
        place.geometry.location.lat,
        place.geometry.location.lng
      ),
      latitude: place.geometry.location.lat,
      longitude: place.geometry.location.lng,
      rating: place.rating,
      openNow: place.opening_hours?.open_now,
    }));

    // Sort by distance
    hospitals.sort((a, b) => a.distance - b.distance);

    return NextResponse.json({ hospitals, isMockData: false });
  } catch (error) {
    console.error('Error fetching nearby hospitals:', error);
    return NextResponse.json(
      { error: 'Failed to fetch nearby hospitals' },
      { status: 500 }
    );
  }
}

// Calculate distance between two coordinates in miles
function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 3959; // Earth's radius in miles
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(R * c * 10) / 10;
}

function toRad(deg: number): number {
  return deg * (Math.PI / 180);
}

// Mock data for hackathon demo
function getMockHospitals(lat: number, lng: number): Hospital[] {
  return [
    {
      name: 'City General Hospital',
      address: '123 Medical Center Dr',
      phone: '(555) 123-4567',
      distance: 1.2,
      latitude: lat + 0.01,
      longitude: lng + 0.01,
      rating: 4.5,
      openNow: true,
    },
    {
      name: 'St. Mary Medical Center',
      address: '456 Healthcare Blvd',
      phone: '(555) 234-5678',
      distance: 2.8,
      latitude: lat + 0.02,
      longitude: lng - 0.01,
      rating: 4.7,
      openNow: true,
    },
    {
      name: 'Regional Emergency Hospital',
      address: '789 Emergency Lane',
      phone: '(555) 345-6789',
      distance: 3.5,
      latitude: lat - 0.02,
      longitude: lng + 0.02,
      rating: 4.3,
      openNow: true,
    },
  ];
}
