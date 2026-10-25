package org.rahat.rahat_mobile

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import java.util.ArrayDeque
import java.util.UUID

@SuppressLint("MissingPermission")
@Suppress("DEPRECATION")
class MainActivity : FlutterActivity() {
    private val serviceId = UUID.fromString("a0000000-0000-1000-8000-f00000000001")
    private val notifyId = UUID.fromString("a0000001-0000-1000-8000-f00000000001")
    private val writeId = UUID.fromString("a0000002-0000-1000-8000-f00000000001")
    private val cccdId = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
    private val handler = Handler(Looper.getMainLooper())
    private var events: EventChannel.EventSink? = null
    private var server: BluetoothGattServer? = null
    private var advertiser: BluetoothLeAdvertiser? = null
    private var notifying: BluetoothGattCharacteristic? = null
    private var starting: MethodChannel.Result? = null
    private val subscribers = mutableMapOf<String, BluetoothDevice>()
    private val notifications = ArrayDeque<Pair<BluetoothDevice, ByteArray>>()
    private var notificationBusy = false
    private var notifyingPeer: String? = null

    private fun emit(data: Map<String, Any>) {
        handler.post { events?.success(data) }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, "org.rahat/ble_mesh_events")
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, sink: EventChannel.EventSink) { events = sink }
                override fun onCancel(arguments: Any?) { events = null }
            })
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "org.rahat/ble_mesh")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "start" -> {
                        if (starting != null) {
                            result.error("BUSY", "Bluetooth relay is already starting", null)
                        } else if (server != null) {
                            result.success(null)
                        } else {
                            starting = result
                            val permissions = if (Build.VERSION.SDK_INT >= 31) {
                                arrayOf(Manifest.permission.BLUETOOTH_SCAN,
                                    Manifest.permission.BLUETOOTH_CONNECT,
                                    Manifest.permission.BLUETOOTH_ADVERTISE)
                            } else {
                                arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
                            }
                            if (Build.VERSION.SDK_INT >= 23 &&
                                permissions.any { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }) {
                                requestPermissions(permissions, 4041)
                            } else startServer()
                        }
                    }
                    "stop" -> {
                        stopServer()
                        result.success(null)
                    }
                    "broadcast" -> {
                        val bytes = call.arguments as? ByteArray
                        if (bytes == null || bytes.size > 16388 || bytes.size < 5) {
                            result.error("INVALID_FRAME", "Invalid relay frame size", null)
                        } else if (server == null) {
                            result.error("STOPPED", "Bluetooth relay is not running", null)
                        } else {
                            val peers = subscribers.values.toList()
                            val needed = ((bytes.size + 19) / 20) * peers.size
                            if (notifications.size + needed > 8192) {
                                result.error("QUEUE_FULL", "Bluetooth transmit queue is full; retry later", null)
                            } else {
                                for (peer in peers) {
                                    for (offset in bytes.indices step 20) {
                                        notifications.add(peer to bytes.copyOfRange(offset, minOf(offset + 20, bytes.size)))
                                    }
                                }
                                pumpNotifications()
                                result.success(peers.size)
                            }
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, results)
        if (requestCode == 4041) {
            if (results.isNotEmpty() && results.all { it == PackageManager.PERMISSION_GRANTED }) {
                startServer()
            } else failStart("PERMISSION_DENIED", "Allow Nearby devices/Bluetooth permission to relay SOS.")
        }
    }

    private fun startServer() {
        try {
            val manager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
            val adapter = manager.adapter
            if (adapter == null || !adapter.isEnabled) {
                failStart("BLUETOOTH_OFF", "Turn on Bluetooth before starting relay.")
                return
            }
            advertiser = adapter.bluetoothLeAdvertiser
            if (advertiser == null) {
                failStart("NO_PERIPHERAL", "This phone does not support BLE peripheral advertising.")
                return
            }
            server = manager.openGattServer(this, callback)
            if (server == null) {
                failStart("NO_SERVER", "Could not open the Bluetooth GATT server.")
                return
            }
            val service = BluetoothGattService(serviceId, BluetoothGattService.SERVICE_TYPE_PRIMARY)
            notifying = BluetoothGattCharacteristic(notifyId,
                BluetoothGattCharacteristic.PROPERTY_NOTIFY, BluetoothGattCharacteristic.PERMISSION_READ)
            notifying!!.addDescriptor(BluetoothGattDescriptor(cccdId,
                BluetoothGattDescriptor.PERMISSION_READ or BluetoothGattDescriptor.PERMISSION_WRITE))
            service.addCharacteristic(notifying)
            service.addCharacteristic(BluetoothGattCharacteristic(writeId,
                BluetoothGattCharacteristic.PROPERTY_WRITE, BluetoothGattCharacteristic.PERMISSION_WRITE))
            if (server?.addService(service) != true) {
                failStart("SERVICE_FAILED", "Could not register the Bluetooth relay service.")
            }
        } catch (error: SecurityException) {
            failStart("PERMISSION_DENIED", error.message ?: "Bluetooth permission was denied.")
        }
    }

    private val advertiseCallback = object : AdvertiseCallback() {
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings) {
            handler.post {
                starting?.success(null)
                starting = null
            }
        }
        override fun onStartFailure(errorCode: Int) {
            handler.post { failStart("ADVERTISE_FAILED", "Bluetooth advertising failed ($errorCode).") }
        }
    }

    private val callback = object : BluetoothGattServerCallback() {
        override fun onServiceAdded(status: Int, service: BluetoothGattService) {
            handler.post {
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    failStart("SERVICE_FAILED", "Bluetooth GATT service registration failed ($status).")
                } else {
                    val settings = AdvertiseSettings.Builder()
                        .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
                        .setConnectable(true)
                        .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_MEDIUM).build()
                    val data = AdvertiseData.Builder().addServiceUuid(ParcelUuid(serviceId)).build()
                    advertiser?.startAdvertising(settings, data, advertiseCallback)
                }
            }
        }

        override fun onConnectionStateChange(device: BluetoothDevice, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                handler.post {
                    subscribers.remove(device.address)
                    notifications.removeAll { it.first.address == device.address }
                    if (notifyingPeer == device.address) {
                        notificationBusy = false
                        notifyingPeer = null
                        pumpNotifications()
                    }
                    emit(mapOf("type" to "disconnected", "peer" to device.address))
                    emit(mapOf("type" to "peers", "count" to subscribers.size))
                }
            }
        }

        override fun onCharacteristicWriteRequest(device: BluetoothDevice, requestId: Int,
            characteristic: BluetoothGattCharacteristic, preparedWrite: Boolean,
            responseNeeded: Boolean, offset: Int, value: ByteArray) {
            val valid = characteristic.uuid == writeId && !preparedWrite && offset == 0 && value.size <= 20
            if (responseNeeded) server?.sendResponse(device, requestId,
                if (valid) BluetoothGatt.GATT_SUCCESS else BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED, 0, null)
            if (valid) emit(mapOf("type" to "bytes", "peer" to device.address, "bytes" to value))
        }

        override fun onDescriptorReadRequest(device: BluetoothDevice, requestId: Int, offset: Int,
            descriptor: BluetoothGattDescriptor) {
            val value = if (subscribers.containsKey(device.address))
                BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE else BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE
            server?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
        }

        override fun onDescriptorWriteRequest(device: BluetoothDevice, requestId: Int,
            descriptor: BluetoothGattDescriptor, preparedWrite: Boolean, responseNeeded: Boolean,
            offset: Int, value: ByteArray) {
            val valid = descriptor.uuid == cccdId && !preparedWrite && offset == 0 && value.size == 2
            if (responseNeeded) server?.sendResponse(device, requestId,
                if (valid) BluetoothGatt.GATT_SUCCESS else BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED, 0, null)
            if (valid) handler.post {
                if (value.contentEquals(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)) {
                    if (subscribers.size < 8) subscribers[device.address] = device
                    else server?.cancelConnection(device)
                } else subscribers.remove(device.address)
                emit(mapOf("type" to "peers", "count" to subscribers.size))
            }
        }

        override fun onNotificationSent(device: BluetoothDevice, status: Int) {
            handler.post {
                if (notifyingPeer != device.address) return@post
                notificationBusy = false
                notifyingPeer = null
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    notifications.removeAll { it.first.address == device.address }
                    server?.cancelConnection(device)
                    emit(mapOf("type" to "error", "message" to "BLE notification interrupted; reconnecting peer."))
                }
                pumpNotifications()
            }
        }
    }

    private fun pumpNotifications() {
        if (notificationBusy || notifications.isEmpty()) return
        val (device, bytes) = notifications.removeFirst()
        val characteristic = notifying ?: return
        characteristic.value = bytes
        notificationBusy = true
        notifyingPeer = device.address
        if (server?.notifyCharacteristicChanged(device, characteristic, false) != true) {
            notificationBusy = false
            notifyingPeer = null
            notifications.removeAll { it.first.address == device.address }
            server?.cancelConnection(device)
            emit(mapOf("type" to "error", "message" to "Could not send BLE data; peer must reconnect."))
            handler.post { pumpNotifications() }
        }
    }

    private fun failStart(code: String, message: String) {
        val result = starting
        starting = null
        stopServer()
        result?.error(code, message, null)
        emit(mapOf("type" to "error", "message" to message))
    }

    private fun stopServer() {
        advertiser?.stopAdvertising(advertiseCallback)
        server?.close()
        server = null
        advertiser = null
        notifying = null
        subscribers.clear()
        notifications.clear()
        notificationBusy = false
        notifyingPeer = null
        starting?.error("CANCELLED", "Bluetooth relay start was cancelled.", null)
        starting = null
    }

    override fun onDestroy() {
        stopServer()
        super.onDestroy()
    }
}
