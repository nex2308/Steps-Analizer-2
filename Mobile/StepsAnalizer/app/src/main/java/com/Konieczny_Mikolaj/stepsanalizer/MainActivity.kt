package com.Konieczny_Mikolaj.stepsanalizer

import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateGroupByPeriodRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.OutputStream
import java.net.Socket
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.Period
import java.time.ZoneId
import java.time.ZonedDateTime

class MainActivity : AppCompatActivity() {

    private lateinit var healthConnectClient: HealthConnectClient
    private lateinit var tvStatus: TextView
    private lateinit var etServerIp: EditText
    private lateinit var btnSend: Button

    // Klucz do SharedPreferences - czy wysłaliśmy już całą historię
    private val PREFS_NAME = "StepsPrefs"
    private val KEY_HISTORY_SENT = "history_sent"

    private val permissions = setOf(
        HealthPermission.getReadPermission(StepsRecord::class)
    )

    private val requestPermissions = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        Log.d("HC_DEBUG", ">>> Callback uprawnień. Otrzymane: $granted")
        if (granted.containsAll(permissions)) {
            setStatus("Uprawnienia przyznane")
            btnSend.isEnabled = true
        } else {
            Log.d("HC_DEBUG", ">>> ODMOWA. Wymagane: $permissions, Otrzymane: $granted")
            setStatus("Brak uprawnień do kroków")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tvStatus = findViewById(R.id.tvStatus)
        etServerIp = findViewById(R.id.etServerIp)
        btnSend = findViewById(R.id.btnSend)

        btnSend.isEnabled = false
        btnSend.setOnClickListener { sendSteps() }

        initHealthConnect()
    }

    private fun initHealthConnect() {
        Log.d("HC_DEBUG", ">>> NOWA WERSJA KODU - start pętli <<<")

        val providers = listOf(
            "com.google.android.apps.healthdata",  // Google Health Connect
            "com.samsung.android.hcapp",           // Samsung Health Connect (One UI 6+)
            ""                                      // Systemowy (Android 14+)
        )

        var sdkStatus = HealthConnectClient.SDK_UNAVAILABLE
        var workingProvider = ""

        for (provider in providers) {
            Log.d("HC_DEBUG", ">>> Sprawdzam provider: '$provider'")
            sdkStatus = if (provider.isEmpty()) {
                HealthConnectClient.getSdkStatus(this)
            } else {
                HealthConnectClient.getSdkStatus(this, provider)
            }
            Log.d("HC_DEBUG", "Provider '$provider' status: $sdkStatus")

            if (sdkStatus == HealthConnectClient.SDK_AVAILABLE) {
                workingProvider = provider
                break
            }
        }
        Log.d("HC_DEBUG", ">>> Czy status == SDK_AVAILABLE: ${sdkStatus == HealthConnectClient.SDK_AVAILABLE}")
        Log.d("HC_DEBUG", ">>> sdkStatus=$sdkStatus, SDK_AVAILABLE=${HealthConnectClient.SDK_AVAILABLE}")

        if (sdkStatus != HealthConnectClient.SDK_AVAILABLE) {
            Log.d("HC_DEBUG", ">>> WCHODZI W RETURN - Health Connect niedostępny")
            setStatus("Health Connect niedostępny (status: $sdkStatus)")
            return
        }

        Log.d("HC_DEBUG", ">>> PRZECHODZI DALEJ - tworzy klienta")
        healthConnectClient = if (workingProvider.isEmpty()) {
            HealthConnectClient.getOrCreate(this)
        } else {
            HealthConnectClient.getOrCreate(this, workingProvider)
        }

        lifecycleScope.launch {
            Log.d("HC_DEBUG", ">>> Sprawdzam przyznane uprawnienia")
            val granted = healthConnectClient.permissionController.getGrantedPermissions()
            Log.d("HC_DEBUG", ">>> Przyznane: $granted")

            if (granted.containsAll(permissions)) {
                Log.d("HC_DEBUG", ">>> Mamy wszystkie uprawnienia!")
                setStatus("Gotowy do wysłania danych")
                btnSend.isEnabled = true
            } else {
                Log.d("HC_DEBUG", ">>> Brak uprawnień - proszę o nie")
                setStatus("Proszę o uprawnienia...")
                requestPermissions.launch(permissions)
            }
        }
    }

    private fun sendSteps() {
        val ip = etServerIp.text.toString().trim()
        if (ip.isEmpty()) {
            Toast.makeText(this, "Wpisz adres IP komputera!", Toast.LENGTH_SHORT).show()
            return
        }

        btnSend.isEnabled = false
        setStatus("Pobieranie danych...")

        lifecycleScope.launch {
            try {
                val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                val historySent = prefs.getBoolean(KEY_HISTORY_SENT, false)

                val stepsMap: Map<String, Long>
                val type: String

                if (!historySent) {
                    // Pierwsze uruchomienie - pobierz całą historię (365 dni)
                    setStatus("Pierwsze uruchomienie - pobieram całą historię...")
                    stepsMap = downloadSteps(daysBack = 365)
                    type = "full_history"
                } else {
                    // Kolejne - tylko ostatnie 7 dni
                    setStatus("Pobieram ostatnie 7 dni...")
                    stepsMap = downloadSteps(daysBack = 7)
                    type = "weekly_update"
                }

                setStatus("Wysyłam ${stepsMap.size} dni danych...")

                val json = JSONObject().apply {
                    put("type", type)
                    put("sent_at", LocalDateTime.now().toString())
                    val stepsJson = JSONObject()
                    stepsMap.forEach { (date, steps) -> stepsJson.put(date, steps) }
                    put("steps", stepsJson)
                }

                val success = sendToServer(ip, 5000, json.toString())

                if (success) {
                    // Zapisz że historia została wysłana
                    prefs.edit().putBoolean(KEY_HISTORY_SENT, true).apply()
                    setStatus("Wysłano ${stepsMap.size} dni danych!\nTyp: $type")
                } else {
                    setStatus("Błąd połączenia z $ip:5000\nSprawdź czy serwer działa")
                }

            } catch (e: Exception) {
                Log.e("HC_DEBUG", "Błąd", e)
                setStatus("Błąd: ${e.message}")
            } finally {
                btnSend.isEnabled = true
            }
        }
    }

    private suspend fun downloadSteps(daysBack: Long): Map<String, Long> {
        return withContext(Dispatchers.IO) {
            val strefa = java.time.ZoneId.systemDefault()

            // Używamy LocalDateTime ale z uwzględnieniem lokalnej strefy
            val czasKoncowy = LocalDateTime.now()
                .withHour(23).withMinute(59).withSecond(59)

            val czasPoczatkowy = czasKoncowy
                .minusDays(daysBack)
                .withHour(0).withMinute(0).withSecond(0)
            val request = AggregateGroupByPeriodRequest(
                metrics = setOf(StepsRecord.COUNT_TOTAL),
                timeRangeFilter = TimeRangeFilter.between(czasPoczatkowy, czasKoncowy),
                timeRangeSlicer = Period.ofDays(1)
            )

            val response = healthConnectClient.aggregateGroupByPeriod(request)
            val stepsMap = mutableMapOf<String, Long>()

            for (dailyResult in response) {
                val date = dailyResult.startTime
                    .atZone(strefa)
                    .toLocalDate()
                    .toString()
                val kroki = dailyResult.result[StepsRecord.COUNT_TOTAL] ?: 0L
                stepsMap[date] = kroki

                // TYMCZASOWY LOG
                Log.d("HC_DEBUG", "Dzień: $date | startTime UTC: ${dailyResult.startTime} | kroki: $kroki")
            }

            Log.d("HC_DEBUG", "Pobrano ${stepsMap.size} dni: ${stepsMap.keys.sorted().takeLast(3)}")
            stepsMap
        }
    }
    private suspend fun sendToServer(ip: String, port: Int, data: String): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                Socket(ip, port).use { socket ->
                    socket.soTimeout = 10000
                    val out: OutputStream = socket.getOutputStream()
                    out.write(data.toByteArray(Charsets.UTF_8))
                    out.flush()
                    socket.shutdownOutput()

                    // Czekaj na potwierdzenie od serwera
                    val response = socket.getInputStream().readBytes().toString(Charsets.UTF_8)
                    Log.d("HC_DEBUG", "Odpowiedź serwera: $response")
                    response == "OK"
                }
            } catch (e: Exception) {
                Log.e("HC_DEBUG", "Błąd połączenia: ${e.message}")
                false
            }
        }
    }

    private fun setStatus(msg: String) {
        runOnUiThread { tvStatus.text = msg }
    }
}