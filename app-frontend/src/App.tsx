import { useState, useRef } from 'react'
import './App.css'

function App() {
  const [isRecording, setIsRecording] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [transcribedText, setTranscribedText] = useState<string>('')
  const [llmResponse, setLlmResponse] = useState<string>('')
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])

  const startRecording = async () => {
    try {
      setError(null)
      setAudioUrl(null)
      setTranscribedText('')
      setLlmResponse('')
      
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' })
        await sendAudioToBackend(audioBlob)
        
        // Stop all tracks to release microphone
        stream.getTracks().forEach(track => track.stop())
      }

      mediaRecorder.start()
      setIsRecording(true)
    } catch (err) {
      setError('Failed to access microphone: ' + (err as Error).message)
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
    }
  }

    const sendAudioToBackend = async (audioBlob: Blob) => {
    setIsProcessing(true)
    try {
      const formData = new FormData()
      formData.append('audio', audioBlob, 'recording.wav')

      const response = await fetch('http://localhost:8000/process-audio', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Backend error: ${response.statusText} - ${errorText}`)
      }

      // Extract metadata from headers
      const transcribed = response.headers.get('X-Transcribed-Text')
      const llmResp = response.headers.get('X-LLM-Response')
      
      if (transcribed) setTranscribedText(decodeURIComponent(transcribed))
      if (llmResp) setLlmResponse(decodeURIComponent(llmResp))

      // Get audio blob from response
      const responseBlob = await response.blob()
      console.log('Audio blob received:', responseBlob.size, 'bytes', responseBlob.type)
      
      // Revoke previous URL if exists
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl)
      }
      
      const url = URL.createObjectURL(responseBlob)
      setAudioUrl(url)
      
      console.log('Audio URL created:', url)
    } catch (err) {
      console.error('Error processing audio:', err)
      setError('Failed to process audio: ' + (err as Error).message)
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <div className="app">
      <h1>AI Voice Assistant</h1>
      
      <div className="controls">
        <button
          onClick={isRecording ? stopRecording : startRecording}
          disabled={isProcessing}
          className={isRecording ? 'recording' : ''}
        >
          {isRecording ? '🔴 Stop Recording' : '🎤 Start Recording'}
        </button>
        
        {isProcessing && <p>Processing your audio...</p>}
      </div>

      {error && (
        <div className="error">
          <p>❌ {error}</p>
        </div>
      )}

      {transcribedText && (
        <div className="result">
          <h3>You said:</h3>
          <p>{transcribedText}</p>
        </div>
      )}

      {llmResponse && (
        <div className="result">
          <h3>AI Response:</h3>
          <p>{llmResponse}</p>
        </div>
      )}

      {audioUrl && (
        <div className="audio-player">
          <h3>Listen to response:</h3>
          <audio controls src={audioUrl} autoPlay>
            Your browser does not support the audio element.
          </audio>
        </div>
      )}
    </div>
  )
}

export default App