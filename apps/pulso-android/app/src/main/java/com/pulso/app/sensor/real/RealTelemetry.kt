package com.pulso.app.sensor.real

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.BatteryManager

data class ImuSample(
    val capturedMonotonicNs: Long,
    val accelerationMps2: List<Float>?,
    val angularVelocityRadps: List<Float>?,
)

/** Captures device IMU event timestamps and the sticky system battery measurement. */
internal class RealTelemetry(context: Context) : SensorEventListener, AutoCloseable {
    private val appContext = context.applicationContext
    private val sensorManager = appContext.getSystemService(SensorManager::class.java)
    @Volatile private var acceleration: Pair<Long, List<Float>>? = null
    @Volatile private var angularVelocity: Pair<Long, List<Float>>? = null
    @Volatile private var battery: Float? = readBattery()
    @Volatile private var batteryTemperatureC: Float? = readBatteryTemperature()

    private val batteryReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            battery = readBattery(intent)
            batteryTemperatureC = readBatteryTemperature(intent)
        }
    }

    fun start() {
        acceleration = null
        angularVelocity = null
        battery = readBattery()
        batteryTemperatureC = readBatteryTemperature()
        sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME)
        }
        sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME)
        }
        appContext.registerReceiver(batteryReceiver, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
    }

    fun batteryFraction(): Float? = battery

    fun batteryTemperatureC(): Float? = batteryTemperatureC

    fun imu(): ImuSample? {
        val accel = acceleration
        val gyro = angularVelocity
        if (accel == null && gyro == null) return null
        return ImuSample(
            capturedMonotonicNs = maxOf(accel?.first ?: 0L, gyro?.first ?: 0L),
            accelerationMps2 = accel?.second,
            angularVelocityRadps = gyro?.second,
        )
    }

    override fun onSensorChanged(event: SensorEvent) {
        val copy = event.values.take(3)
        when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> acceleration = event.timestamp to copy
            Sensor.TYPE_GYROSCOPE -> angularVelocity = event.timestamp to copy
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    override fun close() {
        sensorManager.unregisterListener(this)
        runCatching { appContext.unregisterReceiver(batteryReceiver) }
    }

    private fun readBattery(intent: Intent? = null): Float? {
        val status = intent ?: appContext.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            ?: return null
        val level = status.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = status.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        if (level < 0 || scale <= 0) return null
        return (level.toFloat() / scale).coerceIn(0f, 1f)
    }

    private fun readBatteryTemperature(intent: Intent? = null): Float? {
        val status = intent ?: appContext.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            ?: return null
        val tenthsCelsius = status.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
        return if (tenthsCelsius == Int.MIN_VALUE) null else tenthsCelsius / 10f
    }
}
