import os

output = "test_english.mp3"
print(f"Using local file: {output} ({os.path.getsize(output)} bytes)")

# Test emotion recognition
from audio.emotion import EmotionRecognizer
er = EmotionRecognizer.get_instance()
print("Model initialized:", er._initialized)

result = er.predict(output)
print("Emotion result:", result)

print("Done.")
