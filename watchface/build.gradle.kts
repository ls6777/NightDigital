plugins {
    alias(libs.plugins.android.application)
}

// The release key, from Gradle properties (put them in ~/.gradle/gradle.properties,
// never in this repo) or else from environment variables.
fun releaseSetting(property: String, variable: String): String? =
    providers.gradleProperty(property).orElse(providers.environmentVariable(variable)).orNull

val releaseKeystore = releaseSetting("nightdigital.keystore", "NIGHTDIGITAL_KEYSTORE")
val releaseKeystorePassword = releaseSetting("nightdigital.keystorePassword", "NIGHTDIGITAL_KEYSTORE_PASSWORD")
val releaseKeyAlias = releaseSetting("nightdigital.keyAlias", "NIGHTDIGITAL_KEY_ALIAS")
val releaseKeyPassword = releaseSetting("nightdigital.keyPassword", "NIGHTDIGITAL_KEY_PASSWORD")
val releaseKeyMissing = listOf(releaseKeystore, releaseKeystorePassword, releaseKeyAlias, releaseKeyPassword)
    .any { it.isNullOrEmpty() }

android {
    // Watch Face Format bundles are resource-only: no Kotlin or Java code.
    enableKotlin = false
    namespace = "io.github.ls6777.nightdigital"
    // Watch Face Format version 4 needs Wear OS 6 (API 36) or later.
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.ls6777.nightdigital"
        minSdk = 36
        targetSdk = 36
        versionCode = 2
        versionName = "1.0.1"
    }

    signingConfigs {
        if (!releaseKeyMissing) {
            create("release") {
                storeFile = file(releaseKeystore!!)
                storePassword = releaseKeystorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = true
        }
        release {
            isMinifyEnabled = true
            // Resource shrinking would drop the drawables, which only the
            // watch face XML refers to.
            isShrinkResources = false
            signingConfig = signingConfigs.findByName("release")
        }
    }
}

// Never build an unsigned (or debug-signed) release: stop with the setup steps instead.
tasks.matching { it.name == "preReleaseBuild" }.configureEach {
    val missing = releaseKeyMissing
    doFirst {
        if (missing) {
            throw GradleException(
                "No release key. Set nightdigital.keystore, nightdigital.keystorePassword, " +
                    "nightdigital.keyAlias and nightdigital.keyPassword in ~/.gradle/gradle.properties " +
                    "(or NIGHTDIGITAL_KEYSTORE, NIGHTDIGITAL_KEYSTORE_PASSWORD, NIGHTDIGITAL_KEY_ALIAS and " +
                    "NIGHTDIGITAL_KEY_PASSWORD). See the README."
            )
        }
    }
}
