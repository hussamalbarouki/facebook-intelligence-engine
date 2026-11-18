export interface NewsItem {
  title: string;
  link: string;
  source: string;
  pubDate: string;
  category?: string;
}

export interface ConflictEvent {
  id: string;
  date: string;
  type: string;
  location: string;
  lat: number;
  lon: number;
  description: string;
  source: string;
  fatalities?: number;
}

export interface FlightData {
  callsign: string;
  origin: string;
  lat: number;
  lon: number;
  altitude: number;
  heading: number;
  speed: number;
  type?: string;
}

export interface ShipData {
  name: string;
  mmsi: string;
  type: string;
  lat: number;
  lon: number;
  speed: number;
  heading: number;
  destination?: string;
}

export interface SeismicEvent {
  id: string;
  magnitude: number;
  location: string;
  lat: number;
  lon: number;
  depth: number;
  time: string;
  type: string;
}

export interface CyberEvent {
  date: string;
  actor: string;
  target: string;
  type: string;
  description: string;
  source: string;
}

export interface HumanitarianReport {
  title: string;
  date: string;
  country: string;
  source: string;
  url: string;
  type: string;
}

export interface NuclearFacility {
  name: string;
  country: string;
  type: string;
  status: string;
  lat: number;
  lon: number;
}

