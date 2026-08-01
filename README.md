# Pulso

Pulso busca convertir un teléfono potente en el cerebro de un robot de búsqueda
y rescate. La idea es que el mismo núcleo pueda montarse después en un rover,
un dron o un hexápodo sin rehacer toda la lógica.

Para la primera prueba estamos usando un rover y un Samsung S25 Ultra. El
teléfono se encargará de observar el entorno, mantener el contexto de la misión
y decidir qué información necesita antes de avanzar.

## El problema

Después de un sismo, entrar a una zona con escombros puede poner en riesgo a los
rescatistas. Además, dentro de una estructura dañada no siempre hay GPS, buena
señal ni un mapa disponible.

Queremos que Pulso pueda recorrer un lugar desconocido, construir un mapa a
medida que avanza y acercarse a posibles sobrevivientes sin depender de una
conexión a internet.

## Primer objetivo

La primera versión debe poder:

- descubrir rutas mientras recorre un entorno desconocido;
- detectar indicios de una persona y buscar un mejor punto de observación;
- elegir entre varias rutas usando riesgo, distancia e información esperada;
- detener el movimiento si los sensores detectan un peligro inmediato;
- guardar lo que observó y por qué tomó cada decisión.

Gemma será el encargado de razonar sobre la misión. La navegación de corto
alcance y el frenado seguirán teniendo límites deterministas para que una
respuesta incorrecta del modelo no se convierta directamente en movimiento.

## Componentes iniciales

- **Percepción:** cámara, profundidad, pose e IMU del teléfono.
- **Cerebro:** Gemma ejecutándose localmente y consumiendo solo el contexto útil.
- **Cuerpo:** un rover con una interfaz reemplazable.
- **Simulación:** un entorno de desastre para probar antes de mover hardware.
- **Observabilidad:** una vista para seguir sensores, mapa y decisiones.

El siguiente paso es definir los contratos mínimos entre estas piezas.
