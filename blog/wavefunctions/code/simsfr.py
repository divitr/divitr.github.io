import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from scipy.integrate import solve_ivp

class GaussianWavepacket:
    def __init__(self, x_0, p_0, a, hbar=1, m=1):
        self.x_0 = x_0
        self.sigma = hbar / np.abs(p_0)
        self.p_0 = p_0
        self.a = a
        self.hbar = hbar
        self.m = m

    def initial_wavefunction(self, x):
        gaussian = np.exp(-((x - self.x_0)**2) / (2 * self.a**2))
        phase = np.exp(1j * self.p_0 * x / self.hbar)
        wavefunction = gaussian * phase

        norm = np.sqrt(np.trapz(np.abs(wavefunction)**2, x))
        return wavefunction / norm
    
    def schrodinger_equation(self, t, psi, x, V):
        # Forward/backward differences at edges to prevent reflection
        dx = x[1] - x[0]
        d2psi = np.zeros_like(psi, dtype=complex)
        d2psi[1:-1] = (psi[2:] - 2*psi[1:-1] + psi[:-2]) / (dx**2)
        
        # Use forward/backward differences at boundaries that don't artificially constrain
        d2psi[0] = d2psi[1]
        d2psi[-1] = d2psi[-2]
        
        return -1j * (-self.hbar**2 / (2 * self.m) * d2psi + V * psi)

# Larger domain to give more room
x = np.linspace(-50, 50, 3000)
t = np.linspace(0, 5, 100)

def deltafnpot(x):
    return 0.5 * 0.1*x**2

wavepacket = GaussianWavepacket(x_0=0, p_0=2, a=1)
V = deltafnpot(x)

# Plot setup
fig, ax = plt.subplots(figsize=(12,6))
ax.set_xlim(-20, 20)  # Keep view window small
ax.set_ylim(-1.5, 1.5)

pot, = ax.plot(x, V, color="red", label="V(x)", alpha=0.5)
ax.fill_between(x, V, color="red", alpha=0.3)
re, = ax.plot([], [], color="blue", label="Re(ψ)", linestyle="--", linewidth=1, alpha=0.5)
im, = ax.plot([], [], color="red", label="Im(ψ)", linestyle="--", linewidth=1, alpha=0.5)
pdf, = ax.plot([], [], color="green", label="|ψ|^2", linestyle="-", linewidth=2)
ax.set_xlabel("x")
ax.legend()

# Initialize with the initial wave function
psi_initial = wavepacket.initial_wavefunction(x)

re.set_data(x, np.real(psi_initial))
im.set_data(x, np.imag(psi_initial))
pdf.set_data(x, np.abs(psi_initial)**2)

# Solution array to store wave function
psi_solution = [psi_initial]

def update(frame):
    # Use solve_ivp for numerical integration
    solution = solve_ivp(
        wavepacket.schrodinger_equation, 
        [t[frame-1], t[frame]], 
        psi_solution[-1], 
        args=(x, V),
        method='RK45'
    )
    
    psi = solution.y[:, -1]
    psi_solution.append(psi)
    
    re.set_ydata(np.real(psi))
    im.set_ydata(np.imag(psi))
    pdf.set_ydata(np.abs(psi)**2)
    ax.set_title(f"Gaussian Wavepacket, t={t[frame]:.2f}")
    return re, im, pdf

# Set up the animation
ani = FuncAnimation(fig, update, frames=range(1, len(t)))

plt.tight_layout()
plt.show()