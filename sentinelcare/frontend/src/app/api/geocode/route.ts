import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const { address } = await request.json();

    if (!address) {
      return NextResponse.json(
        { error: 'Address is required' },
        { status: 400 }
      );
    }

    const apiKey = process.env.GOOGLE_MAPS_API_KEY;

    if (!apiKey) {
      // Return mock data for hackathon demo
      return NextResponse.json({
        location: {
          lat: 37.7749,
          lng: -122.4194,
        },
        formattedAddress: address,
        isMockData: true,
      });
    }

    // Use Google Geocoding API
    const encodedAddress = encodeURIComponent(address);
    const url = `https://maps.googleapis.com/maps/api/geocode/json?address=${encodedAddress}&key=${apiKey}`;

    const response = await fetch(url);
    const data = await response.json();

    if (data.status !== 'OK') {
      return NextResponse.json(
        { error: 'Geocoding failed', status: data.status },
        { status: 400 }
      );
    }

    const result = data.results[0];
    return NextResponse.json({
      location: {
        lat: result.geometry.location.lat,
        lng: result.geometry.location.lng,
      },
      formattedAddress: result.formatted_address,
      isMockData: false,
    });
  } catch (error) {
    console.error('Error geocoding address:', error);
    return NextResponse.json(
      { error: 'Failed to geocode address' },
      { status: 500 }
    );
  }
}
