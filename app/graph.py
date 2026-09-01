# graph_fixed_v2.py
"""
Comprehensive Matplotlib Graphing Demo - Fixed for latest matplotlib
All graphs saved in high-quality JPEG format
"""

import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from datetime import datetime
import os
import warnings
warnings.filterwarnings('ignore', category=UserWarning)

# Set matplotlib to use Agg backend (headless)
import matplotlib
matplotlib.use('Agg')

def create_signal_plots():
    """Create various signal processing plots"""
    
    # Create figure with subplots
    fig = plt.figure(figsize=(14, 10), dpi=100)
    gs = GridSpec(3, 3, figure=fig)
    
    # 1. Sine Wave with Noise
    ax1 = fig.add_subplot(gs[0, 0])
    t = np.linspace(0, 2, 500)
    clean = np.sin(2 * np.pi * 5 * t)
    noise = 0.3 * np.random.randn(len(t))
    signal_noisy = clean + noise
    ax1.plot(t, clean, 'b-', label='Clean', alpha=0.7)
    ax1.plot(t, signal_noisy, 'r-', label='Noisy', alpha=0.4)
    ax1.set_title('Sine Wave with Noise')
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Amplitude')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. FFT Spectrum
    ax2 = fig.add_subplot(gs[0, 1])
    freqs = np.fft.fftfreq(len(signal_noisy), t[1] - t[0])
    fft_vals = np.fft.fft(signal_noisy)
    ax2.plot(freqs[:len(freqs)//2], np.abs(fft_vals[:len(freqs)//2]))
    ax2.set_title('FFT Spectrum')
    ax2.set_xlabel('Frequency (Hz)')
    ax2.set_ylabel('Magnitude')
    ax2.grid(True, alpha=0.3)
    
    # 3. Histogram
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.hist(signal_noisy, bins=30, density=True, alpha=0.7, color='green')
    ax3.set_title('Signal Distribution')
    ax3.set_xlabel('Value')
    ax3.set_ylabel('Density')
    ax3.grid(True, alpha=0.3)
    
    # 4. Scatter Plot
    ax4 = fig.add_subplot(gs[1, 0])
    x = np.random.randn(200)
    y = 2 * x + 0.5 * np.random.randn(200)
    ax4.scatter(x, y, alpha=0.6, c=x, cmap='viridis')
    ax4.set_title('Scatter Plot')
    ax4.set_xlabel('X')
    ax4.set_ylabel('Y')
    ax4.grid(True, alpha=0.3)
    
    # 5. Spectrogram
    ax5 = fig.add_subplot(gs[1, 1])
    t_spec = np.linspace(0, 5, 1000)
    f_spec = np.linspace(1, 20, 1000)
    chirp = np.sin(2 * np.pi * f_spec * t_spec)
    f, t_plot, Sxx = signal.spectrogram(chirp, fs=1000, nperseg=128)
    ax5.pcolormesh(t_plot, f, Sxx, shading='gouraud')
    ax5.set_title('Spectrogram')
    ax5.set_xlabel('Time (s)')
    ax5.set_ylabel('Frequency (Hz)')
    
    # 6. Bar Chart
    ax6 = fig.add_subplot(gs[1, 2])
    categories = ['A', 'B', 'C', 'D', 'E']
    values = np.random.randint(10, 50, 5)
    colors = plt.cm.Set3(np.linspace(0, 1, 5))
    ax6.bar(categories, values, color=colors)
    ax6.set_title('Bar Chart')
    ax6.set_xlabel('Category')
    ax6.set_ylabel('Value')
    ax6.grid(True, alpha=0.3, axis='y')
    
    # 7. Multiple Sine Waves
    ax7 = fig.add_subplot(gs[2, 0])
    t_multi = np.linspace(0, 3, 300)
    for freq in [2, 4, 6]:
        ax7.plot(t_multi, np.sin(2 * np.pi * freq * t_multi), 
                label=f'{freq} Hz', alpha=0.7)
    ax7.set_title('Multiple Sine Waves')
    ax7.set_xlabel('Time (s)')
    ax7.set_ylabel('Amplitude')
    ax7.legend()
    ax7.grid(True, alpha=0.3)
    
    # 8. Pie Chart
    ax8 = fig.add_subplot(gs[2, 1])
    sizes = [30, 25, 20, 15, 10]
    labels = ['A', 'B', 'C', 'D', 'E']
    colors = plt.cm.Set3(np.linspace(0, 1, 5))
    ax8.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    ax8.set_title('Pie Chart')
    
    # 9. Error Bars
    ax9 = fig.add_subplot(gs[2, 2])
    x_error = np.arange(5)
    y_error = np.random.randn(5) + 5
    y_err = np.random.rand(5) * 2
    ax9.errorbar(x_error, y_error, yerr=y_err, fmt='o', capsize=5, 
                color='blue', ecolor='red', elinewidth=2, markersize=8)
    ax9.set_title('Error Bars')
    ax9.set_xlabel('X')
    ax9.set_ylabel('Y')
    ax9.grid(True, alpha=0.3)
    
    plt.suptitle('Scientific Python Graphing Demo', fontsize=16, fontweight='bold')
    plt.tight_layout()
    
    return fig

def create_3d_plot():
    """Create a 3D surface plot"""
    fig = plt.figure(figsize=(12, 8), dpi=100)
    ax = fig.add_subplot(111, projection='3d')
    
    # Create data
    x = np.linspace(-5, 5, 50)
    y = np.linspace(-5, 5, 50)
    X, Y = np.meshgrid(x, y)
    R = np.sqrt(X**2 + Y**2)
    Z = np.sin(R) / (R + 0.1)
    
    # Plot surface
    surf = ax.plot_surface(X, Y, Z, cmap='viridis', 
                          linewidth=0, antialiased=True, alpha=0.8)
    
    ax.set_title('3D Surface Plot', fontsize=14, fontweight='bold')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10)
    
    return fig

def create_correlation_plot():
    """Create a correlation heatmap"""
    fig, ax = plt.subplots(figsize=(8, 6), dpi=100)
    
    # Generate correlated data
    np.random.seed(42)
    data = np.random.randn(100, 4)
    data[:, 1] = 0.7 * data[:, 0] + 0.3 * np.random.randn(100)
    data[:, 2] = 0.5 * data[:, 0] + 0.5 * np.random.randn(100)
    data[:, 3] = 0.3 * data[:, 1] + 0.7 * np.random.randn(100)
    
    # Calculate correlation matrix
    corr = np.corrcoef(data.T)
    
    # Create heatmap
    im = ax.imshow(corr, cmap='coolwarm', vmin=-1, vmax=1, aspect='auto')
    
    # Add labels
    ax.set_xticks(range(4))
    ax.set_yticks(range(4))
    ax.set_xticklabels(['Feature 1', 'Feature 2', 'Feature 3', 'Feature 4'])
    ax.set_yticklabels(['Feature 1', 'Feature 2', 'Feature 3', 'Feature 4'])
    
    # Add text annotations
    for i in range(4):
        for j in range(4):
            ax.text(j, i, f'{corr[i, j]:.2f}', 
                   ha='center', va='center',
                   color='white' if abs(corr[i, j]) > 0.5 else 'black')
    
    ax.set_title('Correlation Heatmap', fontsize=14, fontweight='bold')
    fig.colorbar(im, ax=ax, shrink=0.8)
    
    return fig

def create_fourier_analysis_plot():
    """Create Fourier analysis plots for network traffic simulation"""
    fig, axes = plt.subplots(3, 2, figsize=(14, 12), dpi=100)
    
    # Simulate network traffic data
    np.random.seed(42)
    t = np.linspace(0, 100, 1000)
    
    # Traffic patterns: periodic bursts + random noise
    traffic = (
        10 * np.sin(2 * np.pi * 0.1 * t) +  # 10s period
        5 * np.sin(2 * np.pi * 0.02 * t) +   # 50s period
        3 * np.random.randn(len(t))          # Random noise
    )
    traffic = np.maximum(traffic, 0)
    
    # 1. Time series
    ax1 = axes[0, 0]
    ax1.plot(t, traffic, 'b-', alpha=0.7)
    ax1.set_title('Network Traffic Time Series')
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Requests/sec')
    ax1.grid(True, alpha=0.3)
    
    # 2. FFT Spectrum
    ax2 = axes[0, 1]
    freqs = np.fft.fftfreq(len(traffic), t[1] - t[0])
    fft_vals = np.fft.fft(traffic - np.mean(traffic))
    ax2.plot(freqs[:len(freqs)//2], np.abs(fft_vals[:len(freqs)//2]))
    ax2.set_title('FFT Spectrum')
    ax2.set_xlabel('Frequency (Hz)')
    ax2.set_ylabel('Magnitude')
    ax2.grid(True, alpha=0.3)
    
    # Find peaks
    peaks, properties = signal.find_peaks(
        np.abs(fft_vals[:len(freqs)//2]), 
        height=10,
        distance=5
    )
    for peak in peaks:
        ax2.plot(freqs[peak], np.abs(fft_vals[peak]), 'r*', markersize=10)
    
    # 3. Periodogram
    ax3 = axes[1, 0]
    f, Pxx = signal.periodogram(traffic, fs=1.0)
    ax3.semilogy(f, Pxx)
    ax3.set_title('Periodogram')
    ax3.set_xlabel('Frequency (Hz)')
    ax3.set_ylabel('Power Spectral Density')
    ax3.grid(True, alpha=0.3)
    
    # 4. Autocorrelation
    ax4 = axes[1, 1]
    autocorr = np.correlate(traffic - np.mean(traffic), 
                           traffic - np.mean(traffic), 
                           mode='full')
    lags = np.arange(-len(traffic)//2, len(traffic)//2)
    ax4.plot(lags, autocorr[:len(lags)])
    ax4.set_title('Autocorrelation')
    ax4.set_xlabel('Lag')
    ax4.set_ylabel('Correlation')
    ax4.grid(True, alpha=0.3)
    
    # 5. Histogram
    ax5 = axes[2, 0]
    ax5.hist(traffic, bins=30, density=True, alpha=0.7, color='green')
    ax5.set_title('Traffic Distribution')
    ax5.set_xlabel('Requests/sec')
    ax5.set_ylabel('Density')
    ax5.grid(True, alpha=0.3)
    
    # 6. Rolling Statistics
    ax6 = axes[2, 1]
    window = 50
    rolling_mean = np.convolve(traffic, np.ones(window)/window, mode='valid')
    rolling_std = np.array([np.std(traffic[i:i+window]) for i in range(len(traffic)-window+1)])
    ax6.plot(rolling_mean, 'b-', label='Rolling Mean')
    ax6.plot(rolling_std, 'r-', label='Rolling Std')
    ax6.set_title('Rolling Statistics (window=50)')
    ax6.set_xlabel('Time')
    ax6.set_ylabel('Value')
    ax6.legend()
    ax6.grid(True, alpha=0.3)
    
    plt.suptitle('Fourier Analysis for Network Traffic', fontsize=16, fontweight='bold')
    plt.tight_layout()
    
    return fig

def create_real_time_dashboard():
    """Create a real-time dashboard style plot"""
    fig = plt.figure(figsize=(15, 10), dpi=100)
    
    # 1. Main time series
    ax1 = plt.subplot(2, 3, 1)
    t = np.linspace(0, 60, 1000)
    data = np.sin(2 * np.pi * 0.1 * t) + 0.5 * np.random.randn(len(t))
    ax1.plot(t, data, 'b-', linewidth=2)
    ax1.fill_between(t, data - 0.5, data + 0.5, alpha=0.2)
    ax1.set_title('Live Data Stream')
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Value')
    ax1.grid(True, alpha=0.3)
    
    # 2. Gauge meter
    ax2 = plt.subplot(2, 3, 2, projection='polar')
    value = np.random.uniform(0, 100)
    theta = np.linspace(0, np.pi, 100)
    r = np.ones_like(theta)
    ax2.barh(theta, r, height=0.1, color='lightgray')
    ax2.barh(theta[:int(len(theta) * value/100)], 
            r[:int(len(theta) * value/100)], 
            height=0.1, color='red' if value > 80 else 'orange' if value > 50 else 'green')
    ax2.set_ylim(0, 1)
    ax2.set_title(f'Gauge: {value:.1f}%')
    ax2.set_xticklabels([])
    ax2.set_yticklabels([])
    
    # 3. Donut chart
    ax3 = plt.subplot(2, 3, 3)
    sizes = [30, 25, 20, 15, 10]
    labels = ['A', 'B', 'C', 'D', 'E']
    colors = plt.cm.Set3(np.linspace(0, 1, 5))
    wedges, texts, autotexts = ax3.pie(sizes, labels=labels, colors=colors, 
                                       autopct='%1.1f%%', startangle=90,
                                       wedgeprops=dict(width=0.3))
    ax3.set_title('Donut Chart')
    
    # 4. Bar chart with trend
    ax4 = plt.subplot(2, 3, 4)
    categories = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    values = np.random.randint(10, 50, 7)
    bars = ax4.bar(categories, values, color='steelblue')
    for bar, value in zip(bars, values):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f'{value}', ha='center', va='bottom')
    ax4.set_title('Weekly Trend')
    ax4.set_ylabel('Value')
    ax4.grid(True, alpha=0.3, axis='y')
    
    # 5. Scatter with regression
    ax5 = plt.subplot(2, 3, 5)
    x = np.random.randn(100)
    y = 0.8 * x + 0.2 * np.random.randn(100)
    ax5.scatter(x, y, alpha=0.6, c='blue')
    z = np.polyfit(x, y, 1)
    p = np.poly1d(z)
    x_line = np.linspace(x.min(), x.max(), 100)
    ax5.plot(x_line, p(x_line), 'r-', linewidth=2)
    ax5.set_title('Scatter with Regression')
    ax5.set_xlabel('X')
    ax5.set_ylabel('Y')
    ax5.grid(True, alpha=0.3)
    
    # 6. Box plot - FIXED: using set_xticklabels instead of labels parameter
    ax6 = plt.subplot(2, 3, 6)
    data = [np.random.randn(50) + i for i in range(3)]
    bp = ax6.boxplot(data)
    ax6.set_xticklabels(['Group 1', 'Group 2', 'Group 3'])
    ax6.set_title('Box Plot')
    ax6.set_ylabel('Value')
    ax6.grid(True, alpha=0.3, axis='y')
    
    plt.suptitle('Real-Time Dashboard Simulation', fontsize=16, fontweight='bold')
    plt.tight_layout()
    
    return fig

def save_jpg(fig, filename, dpi=150):
    """Save figure as high-quality JPG"""
    fig.savefig(filename, 
                format='jpg',
                dpi=dpi,
                bbox_inches='tight',
                facecolor='white',
                pad_inches=0.1)
    size = os.path.getsize(filename) / 1024
    print(f"   ✅ {filename} ({size:.1f} KB)")

def main():
    print("=" * 60)
    print("MATPLOTLIB GRAPHING DEMO - JPG OUTPUT")
    print("=" * 60)
    
    # Create output directory
    os.makedirs('graphs_jpg', exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print("\nGenerating JPG graphs...")
    
    # 1. Signal Processing Plots
    print("   Creating signal plots...")
    fig1 = create_signal_plots()
    save_jpg(fig1, f'graphs_jpg/signal_plots_{timestamp}.jpg')
    plt.close(fig1)
    
    # 2. 3D Surface Plot
    print("   Creating 3D surface plot...")
    fig2 = create_3d_plot()
    save_jpg(fig2, f'graphs_jpg/3d_plot_{timestamp}.jpg')
    plt.close(fig2)
    
    # 3. Correlation Heatmap
    print("   Creating correlation heatmap...")
    fig3 = create_correlation_plot()
    save_jpg(fig3, f'graphs_jpg/correlation_heatmap_{timestamp}.jpg')
    plt.close(fig3)
    
    # 4. Fourier Analysis
    print("   Creating Fourier analysis...")
    fig4 = create_fourier_analysis_plot()
    save_jpg(fig4, f'graphs_jpg/fourier_analysis_{timestamp}.jpg')
    plt.close(fig4)
    
    # 5. Real-time Dashboard
    print("   Creating real-time dashboard...")
    fig5 = create_real_time_dashboard()
    save_jpg(fig5, f'graphs_jpg/realtime_dashboard_{timestamp}.jpg')
    plt.close(fig5)
    
    # Show file sizes
    print("\nGenerated Files:")
    print("-" * 60)
    total_size = 0
    for filename in sorted(os.listdir('graphs_jpg')):
        if filename.endswith('.jpg'):
            size = os.path.getsize(f'graphs_jpg/{filename}') / 1024
            total_size += size
            print(f"   {filename:45} {size:8.2f} KB")
    print("-" * 60)
    print(f"   {'TOTAL':45} {total_size:8.2f} KB")
    
    print("\n" + "=" * 60)
    print("All graphs created successfully as JPG!")
    print(f"Check the 'graphs_jpg' directory for images")
    print("=" * 60)

if __name__ == "__main__":
    main()
