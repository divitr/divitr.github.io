import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from scipy.integrate import quad

x = np.linspace(-10, 10, 500)
print(x[1] - x[0])
print((x[1] - x[0])**2)
t = np.linspace(0, 10, 1000)
dt = t[1] - t[0]

class GaussianWavepacket:
    def __init__(self, x_0, p_0, a, hbar=1, m=1):
        self.x_0 = x_0
        self.sigma = hbar / np.abs(p_0)
        self.p_0 = p_0
        self.a = a
        self.hbar = hbar
        self.m = m

    def initial_wavefunction(self, x):
        gaussian = np.exp(-((x - self.x_0)**2) / self.a**2)
        phase = np.exp(1j * self.p_0 * x / self.hbar)
        wavefunction = gaussian * phase

        norm = np.sqrt(np.trapz(np.abs(wavefunction)**2, x))
        normalized_wavefunction = wavefunction / norm
        return normalized_wavefunction
    
    def schrodinger_rhs(self, psi, V, x):
        def d2dx2(f, x, h):
            d2f_int = (f[2:] - 2 * f[1:-1] + f[:-2]) / h**2
            d2f_first = (f[1] - 2 * f[0] + f[2]) / h**2
            d2f_last = (f[-3] - 2 * f[-2] + f[-1]) / h**2
            d2f = np.zeros_like(f)
            d2f[1:-1] = d2f_int
            d2f[0] = d2f_first
            d2f[-1] = d2f_last
        
            return d2f

        dx = x[1] - x[0]
        d2psi = d2dx2(psi, x, dx)

        rhs = -1j / self.hbar * (-self.hbar**2 / (2 * self.m) * d2psi + V * psi)

        return rhs
    
    def step(self, psi, V, x, dt=0.01):
        psi_new = psi + dt * self.schrodinger_rhs(psi, V, x)
        norm = np.sqrt(np.trapz(np.abs(psi_new)**2, x))
        normalized_psi = psi_new / norm
        return normalized_psi


wavepacket = GaussianWavepacket(x_0=-4, p_0=2, a=1)

fig = plt.figure()

axes = plt.axes(xlim=(-10,10), ylim=(-3,3))

def deltafnpot(x):
    return np.where((x > 2) & (x < 3), 1, 0)

V = deltafnpot(x)

pot, = axes.plot(x, V, color="red", label="V(x)", alpha=0.5)
re, = axes.plot(x, np.empty_like(x), color="blue", label="Re(ψ)", linestyle="--", linewidth=1, alpha=0.5)
im, = axes.plot(x, np.empty_like(x), color="red", label="Im(ψ)", linestyle="--", linewidth=1, alpha=0.5)
pdf, = axes.plot(x, np.empty_like(x), color="green", label="|ψ|^2", linestyle="-", linewidth=2)
axes.set_xlabel("x")
axes.legend()

psi = wavepacket.initial_wavefunction(x)

def update(t):
    global psi
    psi = wavepacket.step(psi, V, x)#wavepacket.initial_wavefunction(x)
    re.set_ydata(np.real(psi))
    im.set_ydata(np.imag(psi))
    pdf.set_ydata(np.abs(psi)**2)
    axes.set_title(f"Gaussian Wavepacket, t={t:.2f}")
    return re, im, pdf

ani = FuncAnimation(fig, update, frames=t)

plt.show()


    

# t = 0
# y = psi.at(x, t)

# plt.plot(x, np.real(y), color="blue", label="Re(ψ)", linestyle="--", linewidth="1", alpha=.5)
# plt.plot(x, np.imag(y), color="red", label="Im(ψ)", linestyle="--", linewidth="1", alpha=.5)
# plt.plot(x, np.abs(y)**2, color="green", label="|ψ|^2", linestyle="-", linewidth="2")

# plt.xlabel("x")
# plt.title(f"Gaussian Wavepacket, t={t}")
# plt.legend()
# plt.show()
