# test_complete_stack.py
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
import io

print("✅ All imports successful!")

# Generate a complex signal
t = np.linspace(0, 10, 1000)
signal1 = np.sin(2 * np.pi * 2 * t) + 0.5 * np.sin(2 * np.pi * 7 * t)
signal2 = np.cos(2 * np.pi * 3 * t) + 0.3 * np.random.randn(len(t))

# FFT analysis
f, Pxx = signal.periodogram(signal1, fs=100)
print(f"✅ Periodogram: {len(f)} frequency bins")

# Plot to memory
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
ax1.plot(t[:200], signal1[:200])
ax1.set_title("Test Signal 1")
ax2.plot(t[:200], signal2[:200])
ax2.set_title("Test Signal 2")

buf = io.BytesIO()
plt.savefig(buf, format='png')
print(f"✅ Plot generated: {len(buf.getvalue())} bytes")

print("🎉 Full stack working perfectly!")

