# Péndulo de ondas (tuercas + hilo de coser)

Simulación 3D de un péndulo de ondas hecho con tuercas de acero DIN 934 colgadas
en V con hilo de coser de una barra de madera. Es un único `index.html` sin
dependencias (solo carga fuentes de Google Fonts si hay internet).

## Abrirlo en la red local

```bash
cd wave-pendulum
python3 serve.py            # o: python serve.py   (Windows)
```

El script imprime algo como:

```
  En este equipo:   http://localhost:8000
  En la red local:  http://192.168.1.37:8000
```

Abre la dirección de **red local** en el móvil, tablet o proyector conectado a
la misma wifi. Opciones: `--port 8080` para otro puerto. Si tienes instalado
`qrcode` (`pip install qrcode`), también imprime un QR con la dirección.

Si el móvil no conecta, suele ser el cortafuegos: en Windows acepta el aviso de
«Permitir acceso» para Python la primera vez (redes privadas); en macOS, permite
conexiones entrantes a Python.

Sin el script también vale: `python3 -m http.server 8000 --bind 0.0.0.0` dentro
de esta carpeta.

## Dos montajes

- **Tuercas e hilo de coser**: tuercas DIN 934 colgadas en V por el agujero.
- **Pelotas de golf pintadas**: como el [«Pèndol d'ones»](https://otos3.blogspot.com/2013/10/pendol-dones.html)
  de Joan Olivares. 15 pelotas cada 6 cm, cada una colgada de una armella con dos hilos.
  La mitad de arriba alterna rojo, verde y azul y la de abajo negro y amarillo, así que
  a Γ/3 cada grupo enseña arriba un solo color y a Γ/2 una fila es negra y la otra
  amarilla. La tabla de montaje dice de qué color va cada pelota.

Hay dos montajes, **A** y **B**, cada uno con su peso (tuercas o pelotas) y todos sus
parámetros. Los botones «Montaje A / Montaje B» eligen cuál editan los controles, y la
física y la lámina de montaje muestran el elegido. Con «Ver los dos a la vez» el lienzo
se parte en dos (en el móvil, uno encima del otro): los dos se sueltan juntos y comparten
el tiempo, así que se ve en directo cómo cambia el patrón con otros parámetros. Por
defecto A lleva tuercas y B las pelotas del blog. Dentro de cada montaje, cada tipo de
peso recuerda sus propios valores de diseño.

## Qué se puede variar

| Grupo | Control | Efecto |
|---|---|---|
| Diseño | número de péndulos (3–30), ciclo Γ (20–180 s), péndulo más largo | recalcula las longitudes: el péndulo *n* da *K + n* oscilaciones en Γ |
| Tuercas e hilo | tuerca M5–M12, separación, apertura de la V, error de montaje | masa, radio de giro, hilo necesario; errores aleatorios de longitud |
| Lanzamiento | con regla / mismo ángulo, amplitud, rozamiento τ | efecto no lineal de ángulos grandes y amortiguamiento |
| Simulación | velocidad ×0,1–×4 | — |

La línea de tiempo se puede arrastrar para saltar a Γ/4, Γ/3, Γ/2… y la vista
3D se gira arrastrando (vistas: 3D, desde el extremo, desde arriba, de frente y de
perfil, esta última mirando a lo largo de la barra).
El botón «Madera transparente» deja ver lo que tapan la barra y los postes; las
aristas ocultas de la madera se dibujan a trazos.

Debajo hay una tarjeta con la física y una **tabla de montaje** con la
distancia de la barra al centro de cada tuerca y el hilo que hace falta.

## Modelo

- Cada tuerca es un péndulo físico: `θ'' = −(gL/(L² + k²)) sen θ − (2/τ) θ'`,
  con `k` el radio de giro de la tuerca alrededor del eje del agujero.
- Las longitudes de diseño ya corrigen ese `k`, así que sin errores el patrón se
  realinea exactamente cada Γ.
- Integración Runge-Kutta 4 con paso de 2 ms; g = 9,81 m/s².
- La V de cada tuerca debe ser más estrecha que la separación entre tuercas (d < s).
  Si no, los hilos de vecinas se cruzan y no pueden atravesarse. La simulación modela
  cada cruce como un muelle que solo empuja, con la rigidez transversal de los dos
  hilos tensos, `T(1/a + 1/b)` en serie, más un amortiguamiento estimado (ζ = 0,08)
  para el roce. Dibuja los hilos doblados y marca con un círculo cada punto de empuje.
  Con d > s las tuercas se arrastran unas a otras y las ondas no llegan a formarse,
  incluso sin rozamiento.
