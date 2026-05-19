import jax
import jax.numpy as jnp
import matplotlib.pyplot as plt
import numpy as np

print("Initializing JAX...")
jax.config.update('jax_platform_name', 'cpu')

def create_dataset(n_samples=100):
    print(f"\nCreating dataset with {n_samples} samples...")
    x = np.linspace(-5, 5, n_samples).reshape(-1, 1)
    y = np.sin(x) + 0.1 * np.random.randn(n_samples, 1)
    print(f"Dataset shape: x={x.shape}, y={y.shape}")
    return x, y

def init_network_params(width, key):
    print(f"Initializing network parameters for width={width}...")
    keys = jax.random.split(key, 4)
    w1 = jax.random.normal(keys[0], (width, 1)) / np.sqrt(1)
    b1 = jax.random.normal(keys[1], (width,)) / np.sqrt(1)
    w2 = jax.random.normal(keys[2], (1, width)) / np.sqrt(width)
    b2 = jax.random.normal(keys[3], (1,)) / np.sqrt(width)
    return {'w1': w1, 'b1': b1, 'w2': w2, 'b2': b2}

def forward(params, x):
    h = jnp.dot(params['w1'], x.T) + params['b1'][:, None]
    h = jnp.maximum(0, h)
    return jnp.dot(params['w2'], h) + params['b2']  # shape (1, n_points)

def compute_ntk(params, x1, x2):
    print("Computing NTK...")
    width = params['w1'].shape[0]
    
    def flatten_params(params):
        return jnp.concatenate([
            params['w1'].flatten(),
            params['b1'].flatten(),
            params['w2'].flatten(),
            params['b2'].flatten()
        ])
    
    def unflatten_params(flat_params, width):
        w1_size = width
        b1_size = width
        w2_size = width
        b2_size = 1
        
        start = 0
        w1 = flat_params[start:start + w1_size].reshape(width, 1)
        start += w1_size
        b1 = flat_params[start:start + b1_size]
        start += b1_size
        w2 = flat_params[start:start + w2_size].reshape(1, width)
        start += w2_size
        b2 = flat_params[start:start + b2_size]
        
        return {'w1': w1, 'b1': b1, 'w2': w2, 'b2': b2}
    
    def forward_flat(flat_params, x):
        params = unflatten_params(flat_params, width)
        x = x.reshape(1, -1)
        out = forward(params, x)  # shape (1, 1)
        return out.squeeze()  # shape ()
    
    flat_params = flatten_params(params)

    def jacobian_x(x):
        return jax.jacrev(forward_flat, argnums=0)(flat_params, x)
    
    jac1 = jax.vmap(jacobian_x)(x1)  # shape (n1, n_params)
    jac2 = jax.vmap(jacobian_x)(x2)  # shape (n2, n_params)
    
    ntk = jnp.dot(jac1, jac2.T)  # shape (n1, n2)
    print(f"NTK shape: {ntk.shape}")
    return ntk

def compute_ntk_evolution():
    print("\nStarting NTK computation...")
    x, y = create_dataset(n_samples=50)
    x_test = np.linspace(-5, 5, 100).reshape(-1, 1)
    print(f"Test points shape: {x_test.shape}")
    
    widths = [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576]
    ntk_values = []
    
    key = jax.random.PRNGKey(0)
    for width in widths:
        print(f"\nComputing NTK for width={width}...")
        params = init_network_params(width, key)
        ntk = compute_ntk(params, x_test, x_test)
        ntk_values.append(ntk)
    
    return x_test, x, y, ntk_values, widths

def plot_ntk_evolution():
    print("\nGenerating visualization...")
    x_test, x, y, ntk_values, widths = compute_ntk_evolution()
    
    plt.figure(figsize=(15, 10))

    print("Plotting training data...")
    plt.subplot(2, 1, 1)
    plt.scatter(x, y, label='Training Data', alpha=0.6)
    plt.title('Training Data')
    plt.xlabel('x')
    plt.ylabel('y')
    plt.legend()
    
    print("Plotting NTK evolution...")
    plt.subplot(2, 1, 2)
    for i, (width, ntk) in enumerate(zip(widths, ntk_values)):
        print(f"Plotting NTK for width={width}...")
        plt.plot(x_test, np.diag(ntk), label=f'Width = {width}')
    
    plt.title('NTK Evolution with Network Width')
    plt.xlabel('x')
    plt.ylabel('NTK(x, x)')
    plt.legend()
    
    print("\nSaving figure to ntk_evolution.png...")
    plt.tight_layout()
    plt.savefig('ntk_evolution.png')
    plt.close()
    print("Done!")

if __name__ == "__main__":
    print("Starting NTK visualization script...")
    plot_ntk_evolution() 