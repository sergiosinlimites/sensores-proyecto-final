// --- Pinout y constantes ---
const byte PIN_SENSOR        = A1;   // No hace falta pinMode()
const int  TIEMPO_MUESTREO_MS = 100; // ms
const int  N_MUESTRAS         = 100; // muestras por corrida
const int  MAX_CORRIDAS       = 50;  // número máximo de corridas

// --- Memoria para resultados (en SRAM global) ---
float referencia[MAX_CORRIDAS];     // slm
float promedioVolt[MAX_CORRIDAS];   // V
float promedioFlujo[MAX_CORRIDAS];  // slm
float precision_[MAX_CORRIDAS];     // V (desviación)
float exactitud_[MAX_CORRIDAS];     // slm (error abs)
int   nCorridas = 0;
float offsetVoltaje = 0.0f;

// --- Variables de estado ---
float refActual = 0.0;
bool  midiendo  = false;

// --- Prototipos ---
void mensajeBienvenida();
void loop();
void medirPromedio();
float calcularPrecision(const float datos[], float media);
float calcularExactitud(float promedioFlujo, float flujoReal);
void imprimirCSV();

void setup() {
  Serial.begin(9600);
  while (!Serial) ;  // para Leonardo/MKR
  mensajeBienvenida();
}

void loop() {
  if (Serial.available()) {
    // Leer línea entera
    char buf[16];
    byte len = Serial.readBytesUntil('\n', buf, sizeof(buf) - 1);
    buf[len] = '\0';
    // Quitar \r si existe
    if (len && buf[len-1] == '\r') buf[len-1] = '\0';

    // Comando 'q'
    if (strcasecmp(buf, "q") == 0) {
      imprimirCSV();
      while (1) ;  // fin
    }

    // Nuevo valor de referencia
    if (!midiendo && len > 0) {
      refActual = atof(buf);
      Serial.print(F("\n--> Referencia recibida: "));
      Serial.print(refActual, 2);
      Serial.println(F(" slm  (iniciando medición…)\n"));
      midiendo = true;
      medirPromedio();
    }
  }
}

void medirPromedio() {
  static float voltajes[N_MUESTRAS];  // mueve a estático para ahorrar pila
  float sumaVolt = 0.0;
  float sumaFlujo = 0.0;

  Serial.println(F(">> Medición en curso, espera..."));

  // 1) Leer N muestras
  for (int i = 0; i < N_MUESTRAS; i++) {
    int   adc  = analogRead(PIN_SENSOR);
    float volt = adc * 5.0f / 1023.0f;
    float flujo = 212.5f * (volt / 5.0f - 0.1f) - 10.0f;

    voltajes[i] = volt;
    sumaVolt   += volt;
    sumaFlujo  += flujo;

    delay(TIEMPO_MUESTREO_MS);
    Serial.println(volt);
  }

  // 2) Promedios
  float promV   = sumaVolt  / N_MUESTRAS;
  float promF   = sumaFlujo / N_MUESTRAS;

// 3) Si enviaste referencia = 0 → calcular solo offset y salir
if (refActual == 0.0f) {
  offsetVoltaje = promV;
  Serial.print(F("Offset calculado = "));
  Serial.print(offsetVoltaje, 4);
  Serial.println(F(" V\n"));
  Serial.println(F("Envía ahora una referencia > 0"));
  midiendo = false;
  return;  // salimos sin hacer conversión a flujo ni guardar nada
}

  // 3) Precisión y exactitud
  float desv    = calcularPrecision(voltajes, promV);
  float errAbs  = calcularExactitud(promF, refActual);



  // 4) Guardar resultados
  if (nCorridas < MAX_CORRIDAS) {
    referencia[nCorridas]     = refActual;
    promedioVolt[nCorridas]   = promV;
    promedioFlujo[nCorridas]  = promF;
    precision_[nCorridas]     = desv;
    exactitud_[nCorridas]     = errAbs;
    nCorridas++;
  } else {
    Serial.println(F(">> Memoria llena: corrida descartada"));
  }

  // 5) Mostrar por consola
  Serial.print(F("Promedio flujo = "));
  Serial.print(promF, 2);
  Serial.println(F(" slm"));

  Serial.print(F("Precisión (σ) = "));
  Serial.print(desv, 4);
  Serial.println(F(" V"));

  Serial.print(F("Exactitud (abs) = "));
  Serial.print(errAbs, 2);
  Serial.println(F(" slm\n"));

  Serial.println(F("Escribe nueva referencia"));
  midiendo = false;
}

float calcularPrecision(const float datos[], float media) {
  float suma2 = 0.0;
  for (int i = 0; i < N_MUESTRAS; i++) {
    float d = datos[i] - media;
    suma2 += d * d;
  }
  return sqrt(suma2 / (N_MUESTRAS - 1));
}

float calcularExactitud(float promedioFlujo, float flujoReal) {
  return fabs(flujoReal - promedioFlujo);
}

void imprimirCSV() {
  Serial.println(F("\n====== RESULTADOS CSV ======"));
  Serial.println(F("Ref(slm)   FlujoAvg(slm)  VoltAvg(V)  Prec(%)  Exact(%)"));
  for (int i = 0; i < nCorridas; i++) {
    // Prec % = (σ / VoltAvg) ·100
    float p = precision_[i] / promedioVolt[i] * 100.0f;
    // Err % = (Exactitud / FlujoAvg) ·100
    float e = exactitud_[i] / promedioFlujo[i] * 100.0f;
    Serial.print(referencia[i], 2);    Serial.print("       ");
    Serial.print(promedioFlujo[i], 2); Serial.print("         ");
    Serial.print(promedioVolt[i], 2);  Serial.print("       ");
    Serial.print(p, 2);                Serial.print("      ");
    Serial.println(e, 2);
  }
  Serial.println(F("============================"));
  Serial.println(F("Copia y pega en Excel :)"));
}

void mensajeBienvenida() {
  Serial.println(F("=== Calibración de flujo ==="));
  Serial.println(F("Escribe valor del anemómetro (slm) y Enter."));
  
}
