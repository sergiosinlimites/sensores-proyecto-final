const byte PIN_SENSOR = A1;      // Entrada analógica 0‑1023
const byte PIN_MOTOR  =  9;      // Salida PWM 0‑255 (opcional)

const int  TIEMPO_MUESTREO_MS = 100;   // 100 ms entre lecturas
const int  N_MUESTRAS         = 100;   // 100 lecturas por ciclo
const int  MAX_CORRIDAS       = 50;    // Hasta 50 promedios guardados

/* ---------- Memoria para guardar resultados ---------- */
float referencia [MAX_CORRIDAS];
float promedio   [MAX_CORRIDAS];
int   nCorridas  = 0;

/* ---------------calculos de solo un dato-----------*/
bool 

/* ---------- Variables de trabajo ---------- */
String bufferEntrada = "";   // Guarda lo que tecleas
float  refActual     = 0.0;  // Valor del anemómetro en la corrida
bool   midiendo      = false;

void setup() {
  pinMode(PIN_SENSOR, INPUT); 
  Serial.begin(9600);
  while (!Serial);                 // Espera USB en placas Leonardo/MKRs

  mensajeBienvenida();
}

void loop() {

  /* ============= 1. Leer teclado por el Monitor Serie ============= */
  if (Serial.available()) {
    char c = Serial.read();

    // Carácter de fin de línea (Enter)
    if (c == '\n' || c == '\r') {
      bufferEntrada.trim();        // Quita espacios y saltos

      // ¿El usuario quiere terminar?
      if (bufferEntrada.equalsIgnoreCase("q")) {
        imprimirCSV();
        while (true);              // Detiene el programa
      }

      // Si no está midiendo, lo que llegó es la nueva referencia
      if (!midiendo && bufferEntrada.length() > 0) {
        refActual = bufferEntrada.toFloat();
        Serial.print("\n--> Referencia recibida: ");
        Serial.print(refActual, 2);
        Serial.println("  (iniciando medición…)\n");
        midiendo = true;
        medirPromedio();           // Llama a la rutina de medición
      }

      bufferEntrada = "";          // Limpia para la próxima línea
    } else {
      bufferEntrada += c;          // Acumula caracteres
    }
  }
}

/* ============= 2. Medir 100 datos, promediar y guardar ============= */
void medirPromedio() {

  float suma = 0.0;

  for (int i = 0; i < N_MUESTRAS; i++) {

    int   adc   = analogRead(PIN_SENSOR);      // 0‑1023
    float volt  = adc * 5.0 / 1023.0;          // 0‑5 V

    // Conversión SFM3020 → caudal en slm
    float flujo = 212.5 * (volt / 5.0 - 0.1) - 10.0;

    suma += volt;
    delay(TIEMPO_MUESTREO_MS);
  }

  float promedioFlujo = suma / N_MUESTRAS;

  // Guardar si hay espacio
  if (nCorridas < MAX_CORRIDAS) {
    referencia [nCorridas] = refActual;
    promedio  [nCorridas] = promedioFlujo;
    nCorridas++;
  } else {
    Serial.println(">> Memoria llena: no se guardó el dato.");
  }

  Serial.print("Promedio medido = ");
  Serial.print(promedioFlujo, 2);
  Serial.println(" slm");
  Serial.println("\n¿Deseas otra medición?  "
                 "Escribe el nuevo valor del anemómetro "
                 "o 'q' para terminar.\n");

  midiendo = false;                // Vuelve al estado de espera
}

/* ============= 3. Mostrar resultados en CSV al final ============= */
void imprimirCSV() {
  Serial.println("\n====== RESULTADOS ======");
  Serial.println("Anemometro_slm,PromedioSensor_slm");

  for (int i = 0; i < nCorridas; i++) {
    Serial.print(referencia[i], 2);
    Serial.print(",");
    Serial.println(promedio[i], 2);
  }

  Serial.println("========================");
  Serial.println("Copia este bloque y pégalo en Excel :)");
}

/* ---------- Mensaje inicial ---------- */
void mensajeBienvenida() {
  Serial.println("=== Calibración de flujo ===");
  Serial.println("Escribe el valor del anemómetro y pulsa Enter.");
  Serial.println("Para finalizar, escribe:  q  y pulsa Enter.\n");
}
