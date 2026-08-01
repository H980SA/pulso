package com.pulso.app.sensor.real

import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import com.google.ar.core.Coordinates2d
import com.google.ar.core.Frame
import com.google.ar.core.Session
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

internal class ArCameraRenderer(
    private val sessionProvider: () -> Session?,
    private val displayRotationProvider: () -> Int,
    private val onFrame: (Frame) -> Unit,
    private val onFailure: (Throwable) -> Unit,
) : GLSurfaceView.Renderer {
    private val quadVertices = floatBuffer(floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f))
    private val transformedTextureCoordinates = floatBuffer(FloatArray(8))
    private var program = 0
    private var textureId = 0
    private var textureBoundSession: Session? = null
    private var width = 1
    private var height = 1

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        textureId = createExternalTexture()
        program = createProgram(VERTEX_SHADER, FRAGMENT_SHADER)
        textureBoundSession = null
        sessionProvider()?.let(::bindCameraTexture)
        GLES20.glClearColor(0f, 0f, 0f, 1f)
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        this.width = width
        this.height = height
        GLES20.glViewport(0, 0, width, height)
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT or GLES20.GL_DEPTH_BUFFER_BIT)
        val session = sessionProvider() ?: return
        val frame = try {
            if (textureBoundSession !== session) bindCameraTexture(session)
            session.setDisplayGeometry(displayRotationProvider(), width, height)
            session.update()
        } catch (failure: Throwable) {
            onFailure(failure)
            return
        }
        if (frame.hasDisplayGeometryChanged()) {
            frame.transformCoordinates2d(
                Coordinates2d.OPENGL_NORMALIZED_DEVICE_COORDINATES,
                quadVertices,
                Coordinates2d.TEXTURE_NORMALIZED,
                transformedTextureCoordinates,
            )
        }
        drawCamera()
        onFrame(frame)
    }

    private fun bindCameraTexture(session: Session) {
        session.setCameraTextureName(textureId)
        textureBoundSession = session
    }

    private fun drawCamera() {
        GLES20.glDisable(GLES20.GL_DEPTH_TEST)
        GLES20.glDepthMask(false)
        GLES20.glUseProgram(program)
        val position = GLES20.glGetAttribLocation(program, "aPosition")
        val textureCoordinate = GLES20.glGetAttribLocation(program, "aTexCoord")
        GLES20.glEnableVertexAttribArray(position)
        GLES20.glVertexAttribPointer(position, 2, GLES20.GL_FLOAT, false, 0, quadVertices)
        GLES20.glEnableVertexAttribArray(textureCoordinate)
        GLES20.glVertexAttribPointer(textureCoordinate, 2, GLES20.GL_FLOAT, false, 0, transformedTextureCoordinates)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)
        GLES20.glUniform1i(GLES20.glGetUniformLocation(program, "uTexture"), 0)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
        GLES20.glDisableVertexAttribArray(position)
        GLES20.glDisableVertexAttribArray(textureCoordinate)
        GLES20.glDepthMask(true)
    }

    private fun createExternalTexture(): Int {
        val textures = IntArray(1)
        GLES20.glGenTextures(1, textures, 0)
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textures[0])
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)
        return textures[0]
    }

    private fun createProgram(vertex: String, fragment: String): Int {
        fun shader(type: Int, source: String): Int = GLES20.glCreateShader(type).also {
            GLES20.glShaderSource(it, source); GLES20.glCompileShader(it)
        }
        return GLES20.glCreateProgram().also {
            GLES20.glAttachShader(it, shader(GLES20.GL_VERTEX_SHADER, vertex))
            GLES20.glAttachShader(it, shader(GLES20.GL_FRAGMENT_SHADER, fragment))
            GLES20.glLinkProgram(it)
        }
    }

    private companion object {
        fun floatBuffer(values: FloatArray): FloatBuffer = ByteBuffer.allocateDirect(values.size * 4)
            .order(ByteOrder.nativeOrder()).asFloatBuffer().apply { put(values); position(0) }
        const val VERTEX_SHADER = "attribute vec4 aPosition; attribute vec2 aTexCoord; varying vec2 vTexCoord; void main(){ gl_Position=aPosition; vTexCoord=aTexCoord; }"
        const val FRAGMENT_SHADER = "#extension GL_OES_EGL_image_external : require\nprecision mediump float; varying vec2 vTexCoord; uniform samplerExternalOES uTexture; void main(){ gl_FragColor=texture2D(uTexture,vTexCoord); }"
    }
}
