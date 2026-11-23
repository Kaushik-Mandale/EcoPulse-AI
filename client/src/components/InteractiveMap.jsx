import React, { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Crosshair, Maximize2, Minimize2, MapPin } from 'lucide-react';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const taskCoordinates = (task) => {
  const lat = task.latitude ?? task.lat;
  const lng = task.longitude ?? task.lng;
  return Number.isFinite(lat) && Number.isFinite(lng) ? [lat, lng] : null;
};

const InteractiveMap = ({
  center,
  zoom = 14,
  driverLocation,
  tasks = [],
  onCompleteTask,
  userLocation,
  onSelectLocation,
  isPickerMode = false,
  height = '350px',
}) => {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const markersRef = useRef(null);
  const onSelectLocationRef = useRef(onSelectLocation);
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  onSelectLocationRef.current = onSelectLocation;

  const mapCenter = useMemo(() => {
    if (center && center.every(Number.isFinite)) return center;
    if (userLocation && Number.isFinite(userLocation.lat) && Number.isFinite(userLocation.lng)) {
      return [userLocation.lat, userLocation.lng];
    }
    if (driverLocation && driverLocation.every(Number.isFinite)) return driverLocation;
    return tasks.map(taskCoordinates).find(Boolean) || selectedLocation;
  }, [center, driverLocation, tasks, userLocation, selectedLocation]);

  useEffect(() => {
    if (!mapRef.current || !mapCenter || mapInstance.current) return undefined;

    const map = L.map(mapRef.current, {
      center: mapCenter,
      zoom,
      maxZoom: 19,
      zoomControl: true,
      scrollWheelZoom: true,
      preferCanvas: true,
    });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
      detectRetina: true,
    }).addTo(map);
    markersRef.current = L.layerGroup().addTo(map);
    mapInstance.current = map;

    if (isPickerMode && onSelectLocation) {
      map.on('click', (event) => {
        const location = { lat: event.latlng.lat, lng: event.latlng.lng };
        setSelectedLocation([location.lat, location.lng]);
        onSelectLocationRef.current?.(location);
      });
    }

    return () => {
      map.remove();
      mapInstance.current = null;
      markersRef.current = null;
    };
  }, [mapCenter?.[0], mapCenter?.[1], zoom, isPickerMode]);

  useEffect(() => {
    if (!mapInstance.current || !markersRef.current) return;
    const group = markersRef.current;
    group.clearLayers();
    const points = [];

    tasks.forEach((task) => {
      const coordinates = taskCoordinates(task);
      if (!coordinates) return;
      points.push(coordinates);

      const marker = L.marker(coordinates);
      const popup = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = task.name || task.location_name || task.id || 'Assigned task';
      popup.appendChild(title);
      const status = document.createElement('div');
      status.textContent = task.status || '';
      popup.appendChild(status);

      if (onCompleteTask && task.status !== 'Completed') {
        const complete = document.createElement('button');
        complete.type = 'button';
        complete.textContent = 'Mark complete';
        complete.addEventListener('click', () => onCompleteTask(task.id));
        popup.appendChild(complete);
      }

      marker.bindPopup(popup);
      marker.addTo(group);
    });

    if (driverLocation && driverLocation.every(Number.isFinite)) {
      points.push(driverLocation);
      L.marker(driverLocation).bindPopup('Current driver location').addTo(group);
    }
    if (userLocation && Number.isFinite(userLocation.lat) && Number.isFinite(userLocation.lng)) {
      const location = [userLocation.lat, userLocation.lng];
      points.push(location);
      L.marker(location).bindPopup('Selected location').addTo(group);
    }
    if (selectedLocation) {
      points.push(selectedLocation);
      L.marker(selectedLocation).bindPopup('Selected location').addTo(group);
    }
    if (points.length > 1) {
      mapInstance.current.fitBounds(L.latLngBounds(points), { padding: [32, 32], maxZoom: 16 });
    }
  }, [tasks, driverLocation, userLocation, selectedLocation, onCompleteTask]);

  useEffect(() => {
    if (mapInstance.current) {
      window.setTimeout(() => mapInstance.current?.invalidateSize(), 100);
    }
  }, [isFullscreen]);

  const handleGeolocate = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const location = [coords.latitude, coords.longitude];
        setSelectedLocation(location);
        onSelectLocation?.({ lat: coords.latitude, lng: coords.longitude });
        mapInstance.current?.setView(location, 16);
      },
      (error) => console.warn('Unable to access the current location:', error.message),
      { enableHighAccuracy: true, timeout: 15000 },
    );
  };

  return (
    <div
      className={`relative w-full overflow-hidden rounded-2xl border border-slate-200 shadow-sm ${isFullscreen ? 'fixed inset-3 z-[1000] bg-white' : ''}`}
      style={{ height: isFullscreen ? 'auto' : height }}
    >
      {mapCenter ? (
        <div ref={mapRef} className="h-full w-full" />
      ) : (
        <div className="flex h-full min-h-48 flex-col items-center justify-center gap-2 bg-slate-50 p-6 text-center text-sm text-slate-600">
          <MapPin className="h-6 w-6 text-slate-400" />
          <p>Location data is not available.</p>
        </div>
      )}
      <div className="absolute right-3 top-3 z-[500] flex gap-2">
        <button
          type="button"
          onClick={handleGeolocate}
          className="rounded-lg border border-slate-200 bg-white p-2 text-slate-700 shadow-sm"
          title="Use current location"
        >
          <Crosshair className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => setIsFullscreen((value) => !value)}
          className="rounded-lg border border-slate-700 bg-slate-900 p-2 text-white shadow-sm"
          title={isFullscreen ? 'Exit fullscreen' : 'Expand map'}
        >
          {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
};

export default InteractiveMap;
