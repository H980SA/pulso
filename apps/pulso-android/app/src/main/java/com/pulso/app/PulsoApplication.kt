package com.pulso.app

import android.app.Application
import com.pulso.app.runtime.GemmaRuntime

class PulsoApplication : Application() {
    val gemmaRuntime: GemmaRuntime by lazy { GemmaRuntime(this) }
}
