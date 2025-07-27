const byte PIN_SENSOR = A1;      // Entrada analógica 0‑1023
const byte PIN_MOTOR  =  9;      // Salida PWM 0‑255 (opcional)

const int  TIEMPO_MUESTREO_MS = 100;   // 100 ms entre lecturas
const int  N_MUESTRAS         = 100;   // 100 lecturas por ciclo
const int  MAX_CORRIDAS       = 50;    // Hasta 50 promedios guardados

/* ---------- Memoria para guardar resultados ---------- */
float referencia [MAX_CORRIDAS];
float promedio   [MAX_CORRIDAS];
float promedio_flujo   [MAX_CORRIDAS];
float precision   [MAX_CORRIDAS];
float exactitud   [MAX_CORRIDAS];
int   nCorridas  = 0;

/* ---------------calculos de solo un dato-----------*/


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
  if (Serial.available()) {
    String entrada = Serial.readStringUntil('\n'); // Lee hasta salto de línea
    entrada.trim();  // Quita espacios en blanco

    if (entrada.equalsIgnoreCase("q")) {
      imprimirCSV();
      while (true);
    }

    if (!midiendo && entrada.length() > 0) {
      refActual = entrada.toFloat();
      Serial.print("\n--> Referencia recibida: ");
      Serial.print(refActual, 2);
      Serial.println("  (iniciando medición…)\n");
      midiendo = true;
      medirPromedio();
      calcularPrecision();
      calcularExactitud();
    }
  }
}

/* ============= 2. Medir 100 datos, promediar y guardar ============= */
void medirPromedio() {

  float suma = 0.0;
  float suma_flu = 0.0;

  for (int i = 0; i < N_MUESTRAS; i++) {

    int   adc   = analogRead(PIN_SENSOR);      // 0‑1023
    float volt  = adc * 5.0 / 1023.0;          // 0‑5 V

    // Conversión SFM3020 → caudal en slm
    float flujo = 212.5 * (volt / 5.0 - 0.1) - 10.0;

    suma += volt;
    suma_flu += flujo;
    delay(TIEMPO_MUESTREO_MS);
    Serial.println(volt);
  }

  float promedioVoltaje = suma / N_MUESTRAS;
  float promedioFlujo = suma_flu / N_MUESTRAS;

  // Guardar si hay espacio
  if (nCorridas < MAX_CORRIDAS) {
    referencia [nCorridas] = refActual;
    promedio  [nCorridas] = promedioVoltaje;
    promedio_flujo  [nCorridas] = promedioFlujo;
    nCorridas++;
  } else {
    Serial.println(">> Memoria llena: no se guardó el dato.");
  }

  Serial.print("Promedio medido = ");
  Serial.print(promedioFlujo, 2);
  Serial.println("V");
  Serial.println("\n¿Deseas otra medición?  "
                 "Escribe el nuevo valor del anemómetro "
                 "o 'q' para terminar.\n");

  midiendo = false;                // Vuelve al estado de espera
}

/* -------------------caclulo el presicion----------------------------- */

void calcularPrecision() {
  float voltajes[N_MUESTRAS];
  float suma = 0.0;

  // 1. Tomar muestras y calcular suma
  for (int i = 0; i < N_MUESTRAS; i++) {
    int adc = analogRead(PIN_SENSOR);
    float volt = adc * 5.0 / 1023.0;
    voltajes[i] = volt;
    suma += volt;
    delay(TIEMPO_MUESTREO_MS);
  }

  // 2. Calcular media
  float media = suma / N_MUESTRAS;

  // 3. Calcular suma de los cuadrados de las diferencias
  float sumaCuadrados = 0.0;
  for (int i = 0; i < N_MUESTRAS; i++) {
    sumaCuadrados += pow(voltajes[i] - media, 2);
  }

  // 4. Calcular desviación estándar
  float desviacion = sqrt(sumaCuadrados / (N_MUESTRAS - 1));  // o /N_MUESTRAS si es población

  // 5. Guardar si hay espacio
  if ((nCorridas - 1) < MAX_CORRIDAS) {
    precision[nCorridas - 1] = desviacion;  // ← Se guarda en la corrida actual
    Serial.print("Precisión (desviación estándar): ");
    Serial.println(desviacion, 4);
  } else {
    Serial.println(">> Memoria llena: no se guardó la precisión.");
  }
}

/*--------------Calcular exactitud----------------------*/
void calcularExactitud() {
  int index = nCorridas-1;  // Último dato

  if (index >= 0 && index < MAX_CORRIDAS) {
    float valorReal    = referencia[index];  // Anemómetro
    float valorMedido  = promedio_flujo[index];    // Sensor a calibrar

    if (valorReal != 0.0) {
      float errorRelativo = abs(valorMedido - valorReal) / valorReal;
      exactitud[index] = 100.0 - (errorRelativo * 100.0);

      Serial.print("Exactitud del sensor respecto al anemómetro: ");
      Serial.print(exactitud[index], 2);
      Serial.println(" %");
    } else {
      exactitud[index] = 0.0;
      Serial.println("Referencia = 0. No se puede calcular la exactitud.");
    }
  }
}


/* ============= 3. Mostrar resultados en CSV al final ============= */
void imprimirCSV() {
  Serial.println("\n====== RESULTADOS ======");
  Serial.println("Anemometro (slm) , Promedio(V) , Precision(V) , Exactitud(slm)");

  for (int i = 0; i < nCorridas; i++) {


    Serial.print(referencia[i], 2);
    Serial.print(",              ");
    Serial.print(promedio[i], 2);
    Serial.print(",           ");
    Serial.print((precision[i]/promedio[i])*100, 2);
    Serial.print("%");
    Serial.print(exactitud[i]/promedio_flujo[i], 2);
    Serial.println("%");
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
