package com.aicoder.familytracker;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "BootReceiver";
    private static final String PREFS_NAME = "tracker_prefs";
    private static final String KEY_NAME = "tracker_name";
    private static final String KEY_SERVER_URL = "tracker_server_url";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            Log.d(TAG, "Dispositivo encendido - verificando rastreo...");

            SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
            String name = prefs.getString(KEY_NAME, null);
            String serverUrl = prefs.getString(KEY_SERVER_URL, null);

            if (name != null && !name.isEmpty() && serverUrl != null && !serverUrl.isEmpty()) {
                Log.d(TAG, "Reactivando rastreo para: " + name);

                Intent serviceIntent = new Intent(context, TrackingService.class);
                serviceIntent.putExtra("name", name);
                serviceIntent.putExtra("serverUrl", serverUrl);

                context.startForegroundService(serviceIntent);
            } else {
                Log.d(TAG, "No hay rastreo activo para reiniciar");
            }
        }
    }
}
