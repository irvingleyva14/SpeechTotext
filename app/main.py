from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from google.cloud import speech_v1p1beta1 as speech
from dotenv import load_dotenv
import asyncio
import queue

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return {"message": "API de Speech-To-Text funcionando 🚀"}


# Cliente de Google Speech
client = speech.SpeechClient()

config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=48000,
    language_code="es-MX",
    enable_automatic_punctuation=True,
    model="phone_call",
    use_enhanced=True,
)


streaming_config = speech.StreamingRecognitionConfig(
    config=config,
    interim_results=True,
)


@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Cola bloqueante (NO async) para comunicar FastAPI -> hilo de gRPC
    audio_queue: queue.Queue[bytes | None] = queue.Queue()

    loop = asyncio.get_event_loop()

    # Generador síncrono que leerá del hilo de gRPC
    def request_generator():
        while True:
            chunk = audio_queue.get()
            if chunk is None:
                # Señal de fin de audio
                break
            yield speech.StreamingRecognizeRequest(audio_content=chunk)

    # Worker en hilo que hace la llamada a Google
    def stt_worker():
        try:
            responses = client.streaming_recognize(
                streaming_config,
                request_generator()
            )
            for response in responses:
                for result in response.results:
                    transcript = result.alternatives[0].transcript
                    # Enviar texto al WebSocket desde el hilo gRPC
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_json({"text": transcript}),
                        loop,
                    )
        except Exception as e:
            print("❌ Error en transcripción:", e)

    # Ejecutar el worker en un hilo del executor
    worker_future = loop.run_in_executor(None, stt_worker)

    try:
        # Bucle principal: solo recibe audio y lo mete a la cola
        while True:
            data = await websocket.receive_bytes()
            # Si llega audio, lo encolamos para Google
            audio_queue.put(data)

    except WebSocketDisconnect:
        print("🔌 Cliente desconectado")

    finally:
        # Señal de fin de audio al generador de requests
        audio_queue.put(None)
        # Esperar a que el hilo de gRPC termine
        try:
            await asyncio.wrap_future(worker_future)
        except Exception as e:
            print("⚠️ Error al esperar worker:", e)

        print("🧹 WebSocket cerrado en backend")
