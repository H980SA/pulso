plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.1.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.20" apply false
}

// ADK Kotlin 0.6.0 is compiled with Kotlin 2.3 but intentionally emits Kotlin
// 2.1-compatible metadata. Its published graph currently selects stdlib 2.3;
// pin the runtime libraries to the compatibility version used by ADK itself.
allprojects {
    configurations.configureEach {
        resolutionStrategy.force(
            "org.jetbrains.kotlin:kotlin-stdlib:2.1.20",
            "org.jetbrains.kotlin:kotlin-stdlib-jdk7:2.1.20",
            "org.jetbrains.kotlin:kotlin-stdlib-jdk8:2.1.20",
        )
    }
}
