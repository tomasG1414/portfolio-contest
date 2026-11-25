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

## Qué se puede variar

| Grupo | Control | Efecto |
|---|---|---|
| Diseño | número de péndulos (3–30), ciclo Γ (20–180 s), péndulo más largo | recalcula las longitudes: el péndulo *n* da *K + n* oscilaciones en Γ |
| Tuercas e hilo | tuerca M5–M12, separación, apertura de la V, error de montaje | masa, radio de giro, hilo necesario; errores aleatorios de longitud |
| Lanzamiento | con regla / mismo ángulo, amplitud, rozamiento τ | efecto no lineal de ángulos grandes y amortiguamiento |
| Simulación | velocidad ×0,1–×4 | — |

La línea de tiempo se puede arrastrar para saltar a Γ/4, Γ/3, Γ/2… y la vista
3D se gira arrastrando (presets: 3D, desde el extremo, desde arriba, de frente).

Debajo hay una tarjeta con la física y una **tabla de montaje** con la
distancia de la barra al centro de cada tuerca y el hilo que hace falta.

## Modelo

- Cada tuerca es un péndulo físico: `θ'' = −(gL/(L² + k²)) sen θ − (2/τ) θ'`,
  con `k` el radio de giro de la tuerca alrededor del eje del agujero.
- Las longitudes de diseño ya corrigen ese `k`, así que sin errores el patrón se
  realinea exactamente cada Γ.
- Integración Runge-Kutta 4 con paso de 2 ms; g = 9,81 m/s².
- La V de cada tuerca debe ser más estrecha que la separación entre tuercas (d < s).
  Si no, los hilos de vecinas se cruzan y se rozan unas dos veces por oscilación; la
  simulación marca esos roces con un círculo.
