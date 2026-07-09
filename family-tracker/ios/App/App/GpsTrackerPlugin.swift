import Capacitor
import CoreLocation
import UIKit
import BackgroundTasks

@objc(GpsTrackerPlugin)
public class GpsTrackerPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "GpsTrackerPlugin"
    public let jsName = "GpsTracker"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "startTracking", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "stopTracking", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getStatus", returnType: CAPPluginReturnPromise)
    ]
    
    private let locationManager = CLLocationManager()
    private var trackerName: String = ""
    private var serverUrl: String = ""
    private var isTracking = false
    private var lastSendTime: Date = Date.distantPast
    private let sendInterval: TimeInterval = 5 * 60 // 5 minutos
    private let prefsKey = "tracker_prefs"
    private let bgTaskId = "com.aicoder.familytracker.location"
    
    override public func load() {
        // Activar monitoreo de batería
        UIDevice.current.isBatteryMonitoringEnabled = true
        
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        locationManager.distanceFilter = 50 // 50 metros mínimo
        locationManager.allowsBackgroundLocationUpdates = true
        locationManager.pausesLocationUpdatesAutomatically = false
        
        // Registrar tarea de fondo (iOS 13+)
        // NOTA: BGTaskScheduler NO garantiza intervalos exactos de 5 minutos.
        // iOS puede retrasar las tareas según el estado de batería y uso.
        // Como respaldo, didUpdateLocations envía ubicación cuando el GPS se activa.
        if #available(iOS 13.0, *) {
            BGTaskScheduler.shared.register(forTaskWithIdentifier: bgTaskId, using: nil) { task in
                self.handleBackgroundTask(task as! BGProcessingTask)
            }
        }
        
        // Restaurar estado si la app se cerró
        if let saved = UserDefaults.standard.dictionary(forKey: prefsKey) as? [String: String] {
            trackerName = saved["name"] ?? ""
            serverUrl = saved["url"] ?? ""
            if !trackerName.isEmpty && !serverUrl.isEmpty {
                isTracking = true
                startLocationUpdates()
            }
        }
    }
    
    @objc func startTracking(_ call: CAPPluginCall) {
        guard let name = call.getString("name"), !name.trimmingCharacters(in: .whitespaces).isEmpty else {
            call.reject("El nombre es requerido")
            return
        }
        guard let url = call.getString("serverUrl"), !url.trimmingCharacters(in: .whitespaces).isEmpty else {
            call.reject("La URL del servidor es requerida")
            return
        }
        
        trackerName = name.trimmingCharacters(in: .whitespaces)
        serverUrl = url.trimmingCharacters(in: .whitespaces)
        
        // Guardar en UserDefaults
        UserDefaults.standard.set(["name": trackerName, "url": serverUrl], forKey: prefsKey)
        
        // Pedir permiso de ubicación
        locationManager.requestAlwaysAuthorization()
        
        // Iniciar rastreo
        isTracking = true
        lastSendTime = Date.distantPast // Permitir primer envío inmediato
        startLocationUpdates()
        
        call.resolve(["success": true])
    }
    
    @objc func stopTracking(_ call: CAPPluginCall) {
        isTracking = false
        locationManager.stopUpdatingLocation()
        UserDefaults.standard.removeObject(forKey: prefsKey)
        trackerName = ""
        serverUrl = ""
        
        call.resolve(["success": true])
    }
    
    @objc func getStatus(_ call: CAPPluginCall) {
        if isTracking && !trackerName.isEmpty {
            call.resolve(["active": true, "name": trackerName])
        } else {
            call.resolve(["active": false])
        }
    }
    
    private func startLocationUpdates() {
        DispatchQueue.main.async {
            self.locationManager.startUpdatingLocation()
        }
        // Programar tarea de fondo como respaldo (iOS 13+)
        if #available(iOS 13.0, *) {
            scheduleBackgroundTask()
        }
    }
    
    @available(iOS 13.0, *)
    private func scheduleBackgroundTask() {
        let request = BGProcessingTaskRequest(identifier: bgTaskId)
        request.requiresNetworkConnectivity = true
        request.earliestBeginDate = Date(timeIntervalSinceNow: sendInterval)
        
        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            print("[GPS] Error programando tarea de fondo: \(error)")
        }
    }
    
    @available(iOS 13.0, *)
    private func handleBackgroundTask(_ task: BGProcessingTask) {
        // Respetar throttling igual que el delegado
        guard shouldSendNow() else {
            task.setTaskCompleted(success: true)
            self.scheduleBackgroundTask()
            return
        }
        lastSendTime = Date()
        sendCurrentLocation(using: locationManager.location) { success in
            if !success {
                // Si falló, resetear lastSendTime para reintentar antes
                self.lastSendTime = Date.distantPast
            }
            task.setTaskCompleted(success: true)
            self.scheduleBackgroundTask()
        }
        
        task.expirationHandler = {
            task.setTaskCompleted(success: false)
        }
    }
    
    private func sendCurrentLocation(using location: CLLocation?, completion: @escaping (Bool) -> Void) {
        guard let location = location else {
            completion(false)
            return
        }
        
        let batteryLevel: Int = {
            if UIDevice.current.isBatteryMonitoringEnabled {
                let level = UIDevice.current.batteryLevel
                return level >= 0 ? Int(level * 100) : -1
            }
            return -1
        }()
        
        let json: [String: Any] = [
            "name": trackerName,
            "lat": location.coordinate.latitude,
            "lon": location.coordinate.longitude,
            "accuracy": location.horizontalAccuracy,
            "battery": batteryLevel,
            "device": UIDevice.current.model,
            "timestamp": ISO8601DateFormatter().string(from: Date())
        ]
        
        guard let url = URL(string: "\(serverUrl)/api/gps") else {
            completion(false)
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: json)
        } catch {
            completion(false)
            return
        }
        
        let task = URLSession.shared.dataTask(with: request) { data, response, error in
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                print("[GPS] Ubicación enviada: \(self.trackerName)")
                completion(true)
            } else {
                print("[GPS] Error enviando ubicación: \(error?.localizedDescription ?? "desconocido")")
                completion(false)
            }
        }
        task.resume()
    }
    
    /// Verifica si ya pasaron 5 minutos desde el último envío
    private func shouldSendNow() -> Bool {
        return Date().timeIntervalSince(lastSendTime) >= sendInterval
    }
}

// MARK: - CLLocationManagerDelegate
extension GpsTrackerPlugin: CLLocationManagerDelegate {
    public func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard isTracking, let latestLocation = locations.last else { return }
        
        // Throttling: solo enviar si pasaron ≥5 minutos desde el último envío
        guard shouldSendNow() else { return }
        
        lastSendTime = Date()
        
        // Usar la ubicación recibida en el callback, no locationManager.location
        sendCurrentLocation(using: latestLocation) { success in
            if !success {
                print("[GPS] Fallo al enviar, reintentando en siguiente ciclo")
                // Resetear lastSendTime para permitir reintento antes de 5 min
                self.lastSendTime = Date.distantPast
            }
        }
    }
    
    public func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        print("[GPS] Error de ubicación: \(error.localizedDescription)")
    }
    
    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            if isTracking {
                startLocationUpdates()
            }
        case .denied, .restricted:
            print("[GPS] Permiso de ubicación denegado")
            isTracking = false
        default:
            break
        }
    }
}
