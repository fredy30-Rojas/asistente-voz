package com.aicoder.familytracker;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;

@CapacitorPlugin(
    name = "GpsTracker",
    permissions = {
        @Permission(strings = {
            android.Manifest.permission.ACCESS_FINE_LOCATION,
            android.Manifest.permission.ACCESS_COARSE_LOCATION,
            android.Manifest.permission.ACCESS_BACKGROUND_LOCATION,
            android.Manifest.permission.FOREGROUND_SERVICE,
            android.Manifest.permission.FOREGROUND_SERVICE_LOCATION
        })
    }
)
public class GpsTrackerPlugin extends Plugin {

    private static final String PREFS_NAME = "tracker_prefs";
    private static final String KEY_NAME = "tracker_name";
    private static final String KEY_SERVER_URL = "tracker_server_url";

    private SharedPreferences getPrefs() {
        return getContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    @PluginMethod
    public void startTracking(PluginCall call) {
        String name = call.getString("name");
        String serverUrl = call.getString("serverUrl");

        if (name == null || name.trim().isEmpty()) {
            call.reject("El nombre es requerido");
            return;
        }

        if (serverUrl == null || serverUrl.trim().isEmpty()) {
            call.reject("La URL del servidor es requerida");
            return;
        }

        // Guardar en SharedPreferences
        SharedPreferences prefs = getPrefs();
        prefs.edit()
            .putString(KEY_NAME, name.trim())
            .putString(KEY_SERVER_URL, serverUrl.trim())
            .apply();

        // Iniciar el servicio (startForegroundService es idempotente,
        // solo crea el servicio si no está corriendo, o llama onStartCommand si ya corre)
        Context context = getContext();
        Intent intent = new Intent(context, TrackingService.class);
        intent.putExtra("name", name.trim());
        intent.putExtra("serverUrl", serverUrl.trim());

        context.startForegroundService(intent);

        JSObject ret = new JSObject();
        ret.put("success", true);
        call.resolve(ret);
    }

    @PluginMethod
    public void stopTracking(PluginCall call) {
        Context context = getContext();
        Intent intent = new Intent(context, TrackingService.class);
        context.stopService(intent);

        // Limpiar SharedPreferences
        SharedPreferences prefs = getPrefs();
        prefs.edit().clear().apply();

        JSObject ret = new JSObject();
        ret.put("success", true);
        call.resolve(ret);
    }

    @PluginMethod
    public void getStatus(PluginCall call) {
        SharedPreferences prefs = getPrefs();
        String name = prefs.getString(KEY_NAME, null);

        JSObject ret = new JSObject();
        if (name != null && !name.isEmpty()) {
            ret.put("active", true);
            ret.put("name", name);
        } else {
            ret.put("active", false);
        }
        call.resolve(ret);
    }
}
