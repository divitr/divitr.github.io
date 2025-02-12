import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# Parameters
N = 1024  # Increased grid size for better spatial resolution
x = np.linspace(-20, 20, N)  # Wider spatial window
dx = x[1] - x[0]
dt = 0.005
steps_per_frame = 5
num_frames = 300
sigma = 1.0
x0 = -10.0  # Start further left
kx = 500.0  # Higher momentum
m = 1.0
ħ = 1.0

# Enhanced absorbing boundary parameters
abs_width = 200  # Increased width of absorbing region
abs_strength = 1.0  # Much stronger absorption
abs_power = 3.0  # Power for absorption profile (makes it more gradual)

# Initial wavefunction
psi = np.exp(-(x - x0)**2/(2*sigma**2)) * np.exp(1j*kx*x)
psi /= np.sqrt(np.sum(np.abs(psi)**2) * dx)  # Normalize

# Potential with barrier and enhanced absorbing boundaries
def potential(x, t):
    V = np.zeros_like(x)
    
    # Central barrier
    V[(x >= 0) & (x <= 3)] = 5
    
    # Add absorbing boundaries with smoother profile
    absorb_mask = np.zeros_like(x)
    left_region = np.arange(abs_width)
    right_region = np.arange(abs_width)
    
    # Smooth polynomial absorption profile
    absorb_mask[:abs_width] = abs_strength * ((abs_width - left_region)/abs_width)**abs_power
    absorb_mask[-abs_width:] = abs_strength * ((right_region + 1)/abs_width)**abs_power
    
    # Add additional exponential dampening at the very edges
    edge_width = 20
    edge_strength = 2.0
    absorb_mask[:edge_width] *= (1 + edge_strength * (1 - np.arange(edge_width)/edge_width))
    absorb_mask[-edge_width:] *= (1 + edge_strength * (np.arange(edge_width)/edge_width))
    
    V = V.astype(complex)  # Make potential complex-valued
    V.imag = -absorb_mask  # Imaginary component causes absorption
    
    return V

V = potential(x, 0)

# Modified Fourier space setup for non-cyclic boundaries
def pad_array(arr, pad_width):
    # Zero-pad the array to prevent wraparound effects
    return np.pad(arr, pad_width, mode='constant')

def unpad_array(arr, pad_width):
    # Remove padding
    return arr[pad_width:-pad_width]

# Fourier space parameters
pad_width = N // 2  # Increased padding to 50% on each side
k_padded = 2 * np.pi * np.fft.fftfreq(N + 2*pad_width, dx)
kinetic_factor = np.exp(-0.5j * k_padded**2 * dt / m)

# Figure setup
fig, ax = plt.subplots(figsize=(12, 6))

# Initialize plots
pdf_line, = ax.plot(x, np.abs(psi)**2, 'k', label='$|\psi|^2$', lw=1.5)
real_line, = ax.plot(x, np.real(psi), 'b', alpha=0.7, label='Re($\psi$)', lw=1)
imag_line, = ax.plot(x, np.imag(psi), 'r', alpha=0.7, label='Im($\psi$)', lw=1)
pot_line, = ax.plot(x, V.real, 'g--', alpha=0.5, label='Potential', lw=1)
# Add absorption profile visualization
abs_line, = ax.plot(x, -V.imag, 'm:', alpha=0.3, label='Absorption', lw=1)

ax.set_xlim(-20, 20)
ax.set_ylim(-1.5, 5.5)
ax.legend(loc='upper right')
ax.set_xlabel('Position')
ax.set_title('1D Wavepacket Evolution with Enhanced Absorbing Boundaries')

# Animation update function
def animate(frame):
    global psi
    for _ in range(steps_per_frame):
        # Split-step method with zero padding to prevent wraparound
        psi *= np.exp(-1j * V * dt / (2*ħ))
        
        # Pad, transform, apply kinetic evolution, inverse transform, unpad
        psi_padded = pad_array(psi, pad_width)
        psi_padded = np.fft.fft(psi_padded)
        psi_padded *= kinetic_factor
        psi_padded = np.fft.ifft(psi_padded)
        psi = unpad_array(psi_padded, pad_width)
        
        psi *= np.exp(-1j * V * dt / (2*ħ))
    
    # Update plots
    pdf = np.abs(psi)**2
    real_part = np.real(psi)
    imag_part = np.imag(psi)
    
    pdf_line.set_ydata(pdf)
    real_line.set_ydata(real_part)
    imag_line.set_ydata(imag_part)
    
    # Dynamic vertical scaling (only upper limit)
    current_max = max(pdf.max(), np.abs(real_part).max(), np.abs(imag_part).max())
    ax.set_ylim(-1.5, max(5.5, current_max*1.2))
    
    return pdf_line, real_line, imag_line, abs_line

# Create animation
ani = FuncAnimation(fig, animate, frames=num_frames, interval=50, blit=True)
plt.show()