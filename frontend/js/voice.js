/**
 * Voice capture module — Web Audio API mic recording with MediaRecorder.
 * Records WAV-compatible audio for the denoiser + STT pipeline.
 */

const Voice = (() => {
    let mediaRecorder = null;
    let audioChunks = [];
    let stream = null;
    let isRecording = false;

    async function requestMic() {
        if (stream) return stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
            });
            return stream;
        } catch (err) {
            console.error('Microphone access denied:', err);
            throw new Error('Microphone access required for voice input');
        }
    }

    async function startRecording() {
        if (isRecording) return;
        const micStream = await requestMic();
        audioChunks = [];

        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus'
            : 'audio/webm';

        mediaRecorder = new MediaRecorder(micStream, { mimeType });

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.start(250);
        isRecording = true;
    }

    function stopRecording() {
        return new Promise((resolve) => {
            if (!mediaRecorder || !isRecording) {
                resolve(null);
                return;
            }

            mediaRecorder.onstop = () => {
                const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
                isRecording = false;
                resolve(blob);
            };

            mediaRecorder.stop();
        });
    }

    function getState() {
        return isRecording ? 'recording' : 'idle';
    }

    return { startRecording, stopRecording, getState };
})();
