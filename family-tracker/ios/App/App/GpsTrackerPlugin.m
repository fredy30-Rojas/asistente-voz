#import <Capacitor/Capacitor.h>

CAP_PLUGIN(GpsTrackerPlugin, "GpsTracker",
    CAP_PLUGIN_METHOD(startTracking, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(stopTracking, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(getStatus, CAPPluginReturnPromise);
)
