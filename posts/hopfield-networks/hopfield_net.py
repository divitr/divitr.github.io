import numpy as np
import matplotlib.pyplot as plt
import skimage.data
from skimage.color import rgb2gray
from skimage.filters import threshold_mean
from skimage.transform import resize

class HopfieldNetwork:
    def __init__(self, patterns):
        self.patterns = patterns
        self.num_neurons = patterns.shape[1]
        self.weights = self.create_weights(patterns)
            
    def create_weights(self, patterns):
        weights = np.zeros((self.num_neurons, self.num_neurons))
        for pattern in patterns:
            pattern = pattern.reshape(-1, 1)
            weights += np.outer(pattern, pattern)
        np.fill_diagonal(weights, 0)  # no self-connections
        return weights / patterns.shape[0]
    
    def update_state(self, state):
        net_inputs = self.weights @ state
        return np.sign(net_inputs)
    
    def energy(self, state):
        return -0.5 * state @ (self.weights @ state)

    def recall(self, initial_state, max_iterations=10):
        state = initial_state.copy()
        prev_state = None
        
        for _ in range(max_iterations):
            state = self.update_state(state)
            if np.array_equal(state, prev_state):
                break
            prev_state = state.copy()
            
        return state

def get_corrupted_input(input, corruption_level):
    corrupted = np.copy(input)
    mask = np.random.random(size=len(input)) < corruption_level
    corrupted[mask] *= -1
    return corrupted

def preprocessing(img, w=128, h=128):
    img = resize(img, (w, h), mode='reflect')
    thresh = threshold_mean(img)
    binary = img > thresh
    shift = 2 * (binary * 1) - 1
    flatten = np.reshape(shift, (w * h))
    return flatten

def reshape(data):
    dim = int(np.sqrt(len(data)))
    data = np.reshape(data, (dim, dim))
    return data

def plot(data, test, predicted, noise, figsize=(5, 6)):
    data = [reshape(d) for d in data]
    test = [reshape(d) for d in test]
    predicted = [reshape(d) for d in predicted]

    fig, axarr = plt.subplots(len(data), 3, figsize=figsize)
    for i in range(len(data)):
        if i == 0:
            axarr[i, 0].set_title('Train data')
            axarr[i, 1].set_title("Input data")
            axarr[i, 2].set_title('Output data')

        axarr[i, 0].imshow(data[i], cmap='gray')
        axarr[i, 0].axis('off')
        axarr[i, 1].imshow(test[i], cmap='gray')
        axarr[i, 1].axis('off')
        axarr[i, 2].imshow(predicted[i], cmap='gray')
        axarr[i, 2].axis('off')
    
    fig.suptitle(f"Noise: {int(noise * 100)}%", fontweight='bold')

    plt.tight_layout()
    plt.show()

def main():
    camera = skimage.data.camera()
    astronaut = rgb2gray(skimage.data.astronaut())
    horse = skimage.data.horse()
    coffee = rgb2gray(skimage.data.coffee())

    data = [camera, astronaut, horse, coffee]
    data = np.array([preprocessing(d) for d in data])

    model = HopfieldNetwork(data)
    
    corruption_level = 0.1
    noisy_data = [get_corrupted_input(d, corruption_level) for d in data]
    
    predicted = [model.recall(d) for d in noisy_data]
    
    plot(data, noisy_data, predicted, noise=corruption_level)

main()