package com.pulso.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.core.content.ContextCompat
import com.pulso.app.robot.AndroidRealBundle
import com.pulso.app.ui.PulsoScreen
import com.pulso.app.ui.PulsoTheme
import com.pulso.app.ui.PulsoViewModel

class MainActivity : ComponentActivity() {
    private val viewModel: PulsoViewModel by viewModels()
    private lateinit var realBundle: AndroidRealBundle
    private val requestMissionPermissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { /* The sensor source reports any denied capability explicitly. */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        enableEdgeToEdge()
        realBundle = AndroidRealBundle.create(this)
        viewModel.attachRealBundle(realBundle)
        val missingPermissions = MISSION_PERMISSIONS.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missingPermissions.isNotEmpty()) {
            requestMissionPermissions.launch(missingPermissions.toTypedArray())
        }
        setContent {
            PulsoTheme {
                PulsoScreen(viewModel, realBundle.previewView)
            }
        }
    }

    override fun onDestroy() {
        viewModel.detachRealBundle(realBundle)
        realBundle.close()
        super.onDestroy()
    }

    private companion object {
        val MISSION_PERMISSIONS = arrayOf(
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO,
        )
    }
}
