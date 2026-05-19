"""
Heat diffusion on a 1D rod: 3 discretizations x 3 diffusion constants
- PDE: T_t = D T_xx on x in [0, 1]
- Dirichlet BCs: T(0,t)=100, T(1,t)=0
- FTCS explicit scheme with stable dt
- Produces: heat_diffusion_grid.gif
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

# ----------------------------
# Parameters (you can tweak)
# ----------------------------
L = 1.0                        # rod length
left_T, right_T = 100.0, 0.0   # boundary temperatures
Ds = [0.001, 0.01, 0.1]        # diffusion constants (columns)
Ns = [32, 128, 512]             # spatial grid sizes including boundaries (rows)
T_final = .5                 # final physical time to simulate (s)
cfl_safety = 0.9               # fraction of dt_max to use (stability safety)

# Animation
fps = 20                       # frames per second in the GIF
frames = 200                   # number of animation frames
gif_name = "heat_diffusion.gif"

# --------------------------------
# Discretization helpers and data
# --------------------------------
# For each grid N and D we will maintain its current temperature field,
# chosen dt, number of substeps per animation frame, etc.

class RodSim:
    def __init__(self, N, D):
        self.N = N
        self.D = D
        self.x = np.linspace(0.0, L, N)
        self.dx = self.x[1] - self.x[0]

        # Initial condition: interior = 0, boundaries fixed at left_T/right_T
        self.u = np.zeros(N, dtype=float)
        self.u[0]  = left_T
        self.u[-1] = right_T

        # Stable time step for FTCS: dt <= dx^2/(2D)
        if D > 0:
            self.dt_max = self.dx**2 / (2.0 * D)
        else:
            self.dt_max = np.inf
        self.dt = cfl_safety * self.dt_max if D > 0 else 0.0

        # How many substeps per animation update to reach T_final in `frames`
        self.total_steps = int(np.ceil(T_final / max(self.dt, 1e-12))) if D > 0 else 1
        self.steps_per_frame = max(1, self.total_steps // frames)

        # For color normalization
        self.vmin, self.vmax = 0.0, 100.0

    def step_once(self):
        """One FTCS time step with Dirichlet boundary conditions."""
        if self.D == 0.0:
            return
        u = self.u
        un = u.copy()
        alpha = self.D * self.dt / (self.dx * self.dx)
        # interior update (vectorized)
        un[1:-1] = u[1:-1] + alpha * (u[2:] - 2*u[1:-1] + u[:-2])
        # re-enforce boundaries
        un[0]  = left_T
        un[-1] = right_T
        self.u = un

    def advance_n(self, n):
        for _ in range(n):
            self.step_once()

# Build all sims (row-major: rows = Ns, columns = Ds)
sims = [[RodSim(N, D) for D in Ds] for N in Ns]

# ----------------------------
# Set up the figure and axes
# ----------------------------
fig, axes = plt.subplots(len(Ns), len(Ds), figsize=(12, 9), constrained_layout=True)

# If len(Ns)=len(Ds)=1, axes is a single Axes; normalize to 2D array access
if len(Ns) == 1 and len(Ds) == 1:
    axes = np.array([[axes]])
elif len(Ns) == 1:
    axes = np.array([axes])
elif len(Ds) == 1:
    axes = np.array([[ax] for ax in axes])

# Create initial images for each panel using imshow of a 1-row "strip"
images = []
for i_row, N in enumerate(Ns):
    for j_col, D in enumerate(Ds):
        ax = axes[i_row, j_col]
        sim = sims[i_row][j_col]

        # Show as a single-row image for a color map over x
        # shape (1, N), with extent along x from 0 to L
        data = sim.u.reshape(1, -1)
        im = ax.imshow(
            data,
            aspect='auto',
            extent=[0, L, 0, 1],   # x from 0..L; y is a dummy 0..1
            vmin=sim.vmin,
            vmax=sim.vmax,
            origin='lower',
            interpolation='nearest'
        )
        images.append(im)

        # Titles and labels
        if i_row == 0:
            ax.set_title(f"D = {D}")
        if j_col == 0:
            ax.set_ylabel(f"N = {N}\n(grid)")

        # x-axis labels and cosmetic tweaks
        ax.set_xlabel("x")
        ax.set_yticks([])
        ax.set_xlim(0, L)

# Add a shared colorbar
# (Use the last imshow as the mappable, but the vmin/vmax are identical across panels)
cbar = fig.colorbar(images[-1], ax=axes, shrink=0.9)
cbar.set_label("Temperature")

# A prominent title that displays the time
time_text = fig.text(0.5, 0.95, "", ha='center', va='top', fontsize=16, fontweight='bold')

# ----------------------------
# Animation function
# ----------------------------
def init():
    # Nothing special; frames get computed in update
    time_text.set_text("Heat Diffusion Simulation - t = 0.000 s")
    return images + [time_text]

def update(frame_idx):
    # Advance each sim by a fixed number of stable steps per frame
    for i_row, _ in enumerate(Ns):
        for j_col, _ in enumerate(Ds):
            sim = sims[i_row][j_col]
            sim.advance_n(sim.steps_per_frame)
            images[i_row*len(Ds) + j_col].set_data(sim.u.reshape(1, -1))

    # Update shared time annotation (use the sim in [0][0] as reference)
    ref = sims[0][0]
    t_elapsed = ref.steps_per_frame * ref.dt * (frame_idx + 1)
    time_text.set_text(f"Heat Diffusion Simulation - t ≈ {t_elapsed:0.3f} s")
    return images + [time_text]

anim = FuncAnimation(fig, update, init_func=init, frames=frames, interval=1000/fps, blit=False)

# ----------------------------
# Save to GIF
# ----------------------------
print(f"Saving GIF to: {gif_name} ... (this may take a moment)")
anim.save(gif_name, writer=PillowWriter(fps=fps))
print("Done.")
