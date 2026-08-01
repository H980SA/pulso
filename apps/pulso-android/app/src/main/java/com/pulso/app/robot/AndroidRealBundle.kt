package com.pulso.app.robot

import android.app.Activity
import android.opengl.GLSurfaceView
import com.pulso.app.BuildConfig
import com.pulso.app.audio.PhoneAudioActuator
import com.pulso.app.sensor.real.AndroidRealSource

/** Physical integration factory; live motor transport remains build-time opt-in and operator-armed. */
class AndroidRealBundle private constructor(
    val source: AndroidRealSource,
    val actions: AndroidRealActionSink,
    val torch: PhoneTorchActuator,
    val audio: PhoneAudioActuator,
) : AutoCloseable {
    val previewView: GLSurfaceView get() = source.surfaceView

    suspend fun startSensors() {
        source.start()
        audio.startMonitoring()
    }

    suspend fun stopSensors() {
        audio.stopMonitoring()
        source.stop()
    }

    override fun close() {
        source.close()
        actions.close()
    }

    companion object {
        fun create(
            activity: Activity,
            liveMotorTransport: Boolean = false,
        ): AndroidRealBundle {
            val torch = PhoneTorchActuator(activity)
            val source = AndroidRealSource(activity, torch::confirmedState)
            val audio = PhoneAudioActuator(activity)
            val rover = ExomyGatewayClient(
                baseUrl = BuildConfig.ROVER_GATEWAY_URL,
                token = BuildConfig.ROVER_GATEWAY_TOKEN,
                dryRun = !(liveMotorTransport || BuildConfig.ROVER_ACTUATION_ENABLED),
            )
            return AndroidRealBundle(source, AndroidRealActionSink(source, rover, torch, audio), torch, audio)
        }
    }
}
