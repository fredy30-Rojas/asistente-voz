package com.aicoder.familytracker;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.location.Location;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import com.google.android.gms.location.FusedLocationProviderClient;
import com.google.android.gms.location.LocationCallback;
import com.google.android.gms.location.LocationRequest;
import com.google.android.gms.location.LocationResult;
import com.google.android.gms.location.LocationServices;
import com.google.android.gms.location.Priority;

import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class TrackingService extends Service {

    private static final String TAG = "TrackingService";
    private static final long INTERVAL_MS = 5 * 60 * 1000; // 5 minutos
    private static final int NOTIFICATION_ID = 1001;
    private static final String CHANNEL_ID = "family-tracker";
    private static final String PREFS_NAME = "tracker_prefs";
    private static final String KEY_NAME = "tracker_name";
    private static final String KEY_SERVER_URL = "tracker_server_url";

    private FusedLocationProviderClient fusedLocationClient;
    private Handler handler;
    private Runnable locationRunnable;
    private LocationCallback locationCallback;  // Guardado para poder remover en onDestroy
    private String trackerName;
    private String serverUrl;
    private boolean isTracking = false;
    private volatile boolean isDestroyed = false;

    @Override
    public void onCreate() {
        super.onCreate();
        Log.d(TAG, "Servicio creado");

        // Crear canal de notificación (importancia baja para no molestar)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Rastreador Familiar",
                NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Notificación de rastreo GPS activo");
            channel.setShowBadge(false);
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }

        // Inicializar cliente de ubicación de Google Play Services
        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this);
        handler = new Handler(Looper.getMainLooper());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "Servicio iniciado");

        if (intent != null) {
            trackerName = intent.getStringExtra("name");
            serverUrl = intent.getStringExtra("serverUrl");
        }

        // Si no vienen en el intent, leer de SharedPreferences
        if (trackerName == null || trackerName.isEmpty()) {
            SharedPreferences prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
            trackerName = prefs.getString(KEY_NAME, null);
            serverUrl = prefs.getString(KEY_SERVER_URL, null);
        }

        if (trackerName == null || serverUrl == null) {
            Log.e(TAG, "Nombre o URL del servidor no configurados");
            stopSelf();
            return START_NOT_STICKY;
        }

        isDestroyed = false;  // Resetear flag al iniciar

        // Iniciar notificación foreground
        startForeground(NOTIFICATION_ID, buildNotification());

        // Iniciar ciclo de envío de ubicación (solo si no está ya corriendo)
        if (!isTracking) {
            startLocationUpdates();
        } else {
            Log.d(TAG, "Rastreo ya activo, ignorando reinicio");
        }

        return START_STICKY;
    }

    private Notification buildNotification() {
        Intent notificationIntent = new Intent(this, MainActivity.class);
        PendingIntent pendingIntent = PendingIntent.getActivity(
            this, 0, notificationIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Rastreador Familiar")
            .setContentText("Rastreador activo - Enviando ubicación cada 5 minutos")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build();
    }

    private void startLocationUpdates() {
        // Cancelar cualquier ciclo anterior para evitar duplicados
        if (locationRunnable != null) {
            handler.removeCallbacks(locationRunnable);
        }

        isTracking = true;
        locationRunnable = new Runnable() {
            @Override
            public void run() {
                sendCurrentLocation();
                // Programar siguiente ejecución
                handler.postDelayed(this, INTERVAL_MS);
            }
        };
        // Primera ejecución inmediata
        handler.post(locationRunnable);
    }

    private void sendCurrentLocation() {
        Log.d(TAG, "Obteniendo ubicación...");

        // Intentar getLastLocation (pasivo, no gasta batería)
        try {
            fusedLocationClient.getLastLocation()
                .addOnSuccessListener(location -> {
                    if (location != null) {
                        Log.d(TAG, "Ubicación obtenida (pasiva): " + location.getLatitude() + ", " + location.getLongitude());
                        sendToServer(location);
                    } else {
                        Log.d(TAG, "Sin ubicación pasiva, solicitando actualización...");
                        requestSingleUpdate();
                    }
                })
                .addOnFailureListener(e -> {
                    Log.e(TAG, "Error obteniendo ubicación pasiva: " + e.getMessage());
                    requestSingleUpdate();
                });
        } catch (SecurityException e) {
            Log.e(TAG, "Permiso de ubicación denegado: " + e.getMessage());
        }
    }

    private void requestSingleUpdate() {
        try {
            // Remover callback anterior si existe para evitar fugas
            if (locationCallback != null) {
                try {
                    fusedLocationClient.removeLocationUpdates(locationCallback);
                } catch (Exception e) {
                    Log.e(TAG, "Error removiendo callback anterior: " + e.getMessage());
                }
                locationCallback = null;
            }

            LocationRequest locationRequest = new LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 30000)
                .setMinUpdateIntervalMillis(10000)
                .setMaxUpdates(1)
                .build();

            // Guardar referencia para poder remover en onDestroy
            locationCallback = new LocationCallback() {
                @Override
                public void onLocationResult(LocationResult locationResult) {
                    super.onLocationResult(locationResult);
                    try {
                        Location location = locationResult.getLastLocation();
                        if (location != null) {
                            Log.d(TAG, "Ubicación obtenida (activa): " + location.getLatitude() + ", " + location.getLongitude());
                            sendToServer(location);
                        } else {
                            Log.e(TAG, "No se pudo obtener ubicación");
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Error en callback de ubicación: " + e.getMessage());
                    }
                    // Detener actualizaciones después de obtener una
                    try {
                        fusedLocationClient.removeLocationUpdates(this);
                        locationCallback = null;
                    } catch (Exception e) {
                        Log.e(TAG, "Error removiendo location updates: " + e.getMessage());
                    }
                }
            };

            fusedLocationClient.requestLocationUpdates(locationRequest, locationCallback, Looper.getMainLooper());
        } catch (SecurityException e) {
            Log.e(TAG, "Permiso de ubicación denegado: " + e.getMessage());
        } catch (Exception e) {
            Log.e(TAG, "Error solicitando ubicación: " + e.getMessage());
        }
    }

    private void sendToServer(Location location) {
        if (isDestroyed) return;  // No enviar si el servicio ya fue destruido
        new Thread(() -> {
            HttpURLConnection conn = null;
            try {
                // Obtener nivel de batería
                int batteryLevel = -1;
                BatteryManager bm = (BatteryManager) getSystemService(Context.BATTERY_SERVICE);
                if (bm != null) {
                    batteryLevel = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
                }

                // Construir JSON
                JSONObject json = new JSONObject();
                json.put("name", trackerName);
                json.put("lat", location.getLatitude());
                json.put("lon", location.getLongitude());
                json.put("accuracy", location.getAccuracy());
                json.put("battery", batteryLevel);
                json.put("device", Build.MODEL);
                json.put("timestamp", getISO8601Timestamp());

                // Enviar al servidor
                String urlStr = serverUrl + "/api/gps";
                URL url = new URL(urlStr);
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(10000);
                conn.setDoOutput(true);

                String jsonStr = json.toString();
                OutputStream os = conn.getOutputStream();
                os.write(jsonStr.getBytes("UTF-8"));
                os.flush();
                os.close();

                int responseCode = conn.getResponseCode();
                if (responseCode == 200) {
                    Log.d(TAG, "Ubicación enviada exitosamente: " + trackerName);
                } else {
                    Log.e(TAG, "Error del servidor: " + responseCode);
                }
            } catch (Exception e) {
                Log.e(TAG, "Error enviando ubicación: " + e.getMessage());
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }).start();
    }

    private String getISO8601Timestamp() {
        SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
        sdf.setTimeZone(TimeZone.getTimeZone("UTC"));
        return sdf.format(new Date());
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        Log.d(TAG, "Servicio destruido");
        isTracking = false;
        isDestroyed = true;
        if (handler != null && locationRunnable != null) {
            handler.removeCallbacks(locationRunnable);
            locationRunnable = null;
        }
        // Remover callback de ubicación pendiente si existe
        if (locationCallback != null) {
            try {
                fusedLocationClient.removeLocationUpdates(locationCallback);
            } catch (Exception e) {
                Log.e(TAG, "Error removiendo callback en onDestroy: " + e.getMessage());
            }
            locationCallback = null;
        }
        // Limpiar handler para evitar fugas
        if (handler != null) {
            handler.removeCallbacksAndMessages(null);
        }
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
