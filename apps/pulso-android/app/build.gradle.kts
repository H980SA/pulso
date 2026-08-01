plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val pulsoHilUrl = providers.gradleProperty("pulsoHilUrl")
    .orElse(providers.environmentVariable("PULSO_HIL_URL"))
    .orElse("ws://127.0.0.1:9091")
    .get()
require(pulsoHilUrl.startsWith("ws://") || pulsoHilUrl.startsWith("wss://")) {
    "pulsoHilUrl must use ws:// or wss://"
}
val pulsoHilUrlLiteral = "\"${pulsoHilUrl.replace("\\", "\\\\").replace("\"", "\\\"")}\""
val pulsoSimHilUrl = providers.gradleProperty("pulsoSimHilUrl")
    .orElse(providers.environmentVariable("PULSO_SIM_HIL_URL"))
    .orElse("ws://127.0.0.1:9092")
    .get()
require(pulsoSimHilUrl.startsWith("ws://") || pulsoSimHilUrl.startsWith("wss://")) {
    "pulsoSimHilUrl must use ws:// or wss://"
}
val pulsoSimHilUrlLiteral = "\"${pulsoSimHilUrl.replace("\\", "\\\\").replace("\"", "\\\"")}\""
val pulsoRoverUrl = providers.gradleProperty("pulsoRoverUrl")
    .orElse(providers.environmentVariable("PULSO_ROVER_URL"))
    .orElse("http://10.245.145.36:8765")
    .get()
require(pulsoRoverUrl.startsWith("http://") || pulsoRoverUrl.startsWith("https://")) {
    "pulsoRoverUrl must use http:// or https://"
}
val pulsoRoverUrlLiteral = "\"${pulsoRoverUrl.replace("\\", "\\\\").replace("\"", "\\\"")}\""
val pulsoRoverToken = providers.gradleProperty("pulsoRoverToken")
    .orElse(providers.environmentVariable("PULSO_ROVER_TOKEN"))
    .orElse("")
    .get()
val pulsoRoverTokenLiteral = "\"${pulsoRoverToken.replace("\\", "\\\\").replace("\"", "\\\"")}\""
val pulsoRoverActuationEnabled = providers.gradleProperty("pulsoRoverActuationEnabled")
    .orElse(providers.environmentVariable("PULSO_ROVER_ACTUATION_ENABLED"))
    .orElse("false")
    .map(String::toBooleanStrict)
    .get()

android {
    namespace = "com.pulso.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.pulso.app"
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "DEFAULT_HIL_URL", pulsoHilUrlLiteral)
        buildConfigField("String", "SIM_HIL_URL", pulsoSimHilUrlLiteral)
        buildConfigField("String", "ROVER_GATEWAY_URL", pulsoRoverUrlLiteral)
        buildConfigField("String", "ROVER_GATEWAY_TOKEN", pulsoRoverTokenLiteral)
        buildConfigField("boolean", "ROVER_ACTUATION_ENABLED", pulsoRoverActuationEnabled.toString())

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables.useSupportLibrary = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
        // LiteRT-LM 0.13.1 is built with Kotlin 2.3 while ADK guarantees a
        // Kotlin 2.1-compatible surface. This is the compatibility flag used
        // by the upstream ADK build itself.
        freeCompilerArgs += "-Xskip-metadata-version-check"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
            merges += "**/META-INF/INDEX.LIST"
            merges += "**/META-INF/DEPENDENCIES"
        }
    }

    testOptions { unitTests.isIncludeAndroidResources = true }
}

dependencies {
    // ADK 0.6.0 publishes these as runtime dependencies in its Android variant,
    // so consumers that use the public types must declare them for compilation.
    implementation("com.google.adk:google-adk-kotlin-core:0.6.0")
    implementation("com.google.adk:google-adk-kotlin-litertlm:0.6.0")
    implementation("com.google.ai.edge.litertlm:litertlm-android:0.13.1")
    implementation("com.google.ar:core:1.54.0")
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.27.0")

    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    implementation(platform("androidx.compose:compose-bom:2024.09.03"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    debugImplementation("androidx.compose.ui:ui-tooling")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.11.0")
}
