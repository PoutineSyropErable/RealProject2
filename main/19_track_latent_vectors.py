import pickle
import argparse

import torch
import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt

from typing import Tuple
from __TRAINING_FILE import EPOCH_WHERE_SAVE_ALL

from __TRAINING_FILE import (
    MeshEncoder,
    SDFCalculator,
    CustomLRScheduler,
    DummyScheduler,
    TrainingContext,
    LATENT_DIM,
    DEFAULT_FINGER_INDEX,
    NEURAL_WEIGHTS_DIR,
)

from visualize_array import show_numpy_array_table

GRID_DIM = 100
DEBUG_ = 0


# Directory containing the pickle files
LOAD_DIR = "./training_data"

# Directory where we save and load the neural weights
FINGER_INDEX = 730


def read_pickle(directory, filename, finger_index, validate=False):
    long_file_name = f"{directory}/{filename}_{finger_index}{'_validate' if validate else ''}.pkl"
    print(long_file_name, "\n")

    with open(long_file_name, "rb") as file:
        output = pickle.load(file)
        print(f"Loaded {type(output)} from {long_file_name}")

    return output


def compute_latent_vector_stats(mesh_encoder, vertices_tensor) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute latent vectors, their relative changes, and orders based on the relative standard deviation.

    Args:
        mesh_encoder (MeshEncoder): The trained mesh encoder model.
        vertices_tensor (torch.Tensor): Tensor of vertices (time_steps, num_vertices, 3).

    Returns:
        tuple: (latent_vectors, order, change_rel, change_rel_order)
            latent_vectors: np.ndarray of shape (latent_dim, time_steps)
            order: Indices of latent vector coordinates ordered by relative change.
            change_rel: Relative change (std / mean) of each latent vector coordinate.
            change_rel_order: Relative change values in descending order.

    return latent_vectors, order, change_rel, change_rel_order
    """
    latent_vector_list = []

    for i in range(len(vertices_tensor)):
        vertices = vertices_tensor[i].view(1, -1)  # Flatten vertices
        latent_vector = mesh_encoder(vertices)  # Extract latent vector
        latent_vector_np = latent_vector.detach().cpu().numpy().flatten()
        if DEBUG_ >= 2:
            print(f"{i}: latent_vector_np = {latent_vector_np}")
        latent_vector_list.append(latent_vector_np)

    latent_vectors = np.array(latent_vector_list).T  # Transpose for easier computation
    if DEBUG_ >= 2:
        print(f"np.shape(latent_vectors) = {np.shape(latent_vectors)}")
        print(f"latent_vectors = \n{latent_vectors}")
    stdl = np.std(latent_vectors, axis=1)  # Standard deviation of each coordinate
    meanl = np.mean(latent_vectors, axis=1)  # Mean of each coordinate

    if DEBUG_ >= 2:
        print("\n")
        print(f"stdl = {stdl}")
        print(f"np.shape(stdl) = {np.shape(stdl)}")

    change_rel = stdl / np.abs(meanl)  # Compute relative change (std / mean)
    change_rel[np.isnan(change_rel)] = 0  # Handle division by zero if mean is zero

    order = np.argsort(change_rel)[::-1]  # Descending order
    change_rel_order = change_rel[order]

    if DEBUG_ >= 2:
        print("\n")
    return latent_vectors, order, change_rel, change_rel_order


def plot_latent_vector_stats(latent_vectors, order, change_rel, change_rel_order, epoch_index):
    """
    Visualize the latent vectors and their relative changes.

    Args:
        latent_vectors (np.ndarray): Latent vectors of shape (latent_dim, time_steps).
        order (np.ndarray): Indices of latent vector coordinates ordered by relative change.
        change_rel (np.ndarray): Relative change of each latent vector coordinate.
        change_rel_order (np.ndarray): Relative change values in descending order.
        epoch_index (int): Epoch index for labeling the plots.
    """
    # Plot relative change (unordered)
    plt.figure()
    plt.title(f"Relative Change (std / mean) of Latent Vector Coordinates [Unordered] (Epoch {epoch_index})", fontsize=16)
    plt.xlabel("Latent Vector Coordinate", fontsize=12)
    plt.ylabel("Relative Change", fontsize=12)
    plt.plot(change_rel, marker="o")
    plt.grid(True)
    plt.show()

    # Plot relative change (ordered)
    plt.figure()
    plt.title(f"Relative Change (std / mean) of Latent Vector Coordinates [Ordered] (Epoch {epoch_index})", fontsize=16)
    plt.xlabel("Latent Vector Coordinate", fontsize=12)
    plt.ylabel("Relative Change", fontsize=12)
    plt.plot(change_rel_order, marker="o")
    plt.grid(True)
    plt.show()

    # Plot trajectory of top 5 latent vector coordinates with highest relative change
    plt.figure()
    plt.title(f"Top 5 Latent Vector Coordinates with Highest Relative Change (Epoch {epoch_index})", fontsize=16)
    plt.xlabel("Time index", fontsize=12)
    plt.ylabel("Latent Value", fontsize=12)
    for i in range(5):
        plt.plot(latent_vectors[order[i]], label=f"Coord {order[i]}, Rel_Change: {change_rel_order[i]:.4f}")
    # plt.legend(loc="upper right")
    plt.grid(True)
    plt.show()


def find_closest_elements(sorted_array, value):
    idx = np.searchsorted(sorted_array, value)

    # Find closest smaller and larger indices
    smaller_idx = idx - 1 if idx > 0 else None
    larger_idx = idx if idx < len(sorted_array) else None

    return smaller_idx, larger_idx


def plot_relative_change_all_epochs(order_rel_changes_all_epochs, num_coords, epochs, start, end, ordered=False):
    """
    Plot the ordered relative change for all epochs in one figure using a red-to-blue color mapping.

    Args:
        order_rel_changes_all_epochs (list of np.ndarray): List of ordered relative changes for each epoch.
        num_coords (int): Number of latent vector coordinates to display (top N).
        epochs (list of int): List of epoch indices.
    """
    order_string = "Ordered " if ordered else ""
    order_latent_string = "(sorted by relative change)" if ordered else ""
    plt.figure(figsize=(12, 8))
    plt.title(f"{order_string}Relative Change of Latent Vectors Across Epochs", fontsize=16)
    plt.xlabel(f"Latent Vector Coordinate {order_latent_string}", fontsize=12)
    plt.ylabel("Relative Change", fontsize=12)

    sis, sib = find_closest_elements(epochs, start)
    eis, eib = find_closest_elements(epochs, end)

    start = sis
    end = eis
    epochs = epochs[start:end]
    order_rel_changes_all_epochs = order_rel_changes_all_epochs[start:end]
    # Normalize colors across epochs
    colors = plt.cm.cool(np.linspace(0, 1, len(epochs)))  # Red-to-blue colormap

    for i, (change_rel_order, epoch) in enumerate(zip(order_rel_changes_all_epochs, epochs)):
        if i == 0 or i == (len(epochs) - 1):
            plt.plot(change_rel_order[:num_coords], label=f"Epoch {epoch}", color=colors[i])
        else:
            plt.plot(change_rel_order[:num_coords], color=colors[i])

    plt.grid(True)
    plt.legend(title="Epoch", loc="upper right", fontsize=10)
    plt.show()


def find_mean_order(all_order: np.ndarray):

    print(f"np.shape(all_order) = {np.shape(all_order)}")
    print(f"all_order = \n{all_order}\n")

    shape = np.shape(all_order)
    order_counts = np.zeros(shape=(shape[1], shape[1]))
    for epoch in range(shape[0]):
        for position in range(shape[1]):
            latent_index = all_order[epoch, position]
            order_counts[latent_index, position] += 1

    print(f"np.shape(order_counts) = {np.shape(order_counts)}")
    print(f"order_counts = \n{order_counts}\n")

    mean_order = np.mean(order_counts, axis=1)

    return mean_order


def track_latent_rel_change_over_epoch(epoch_list, rel_changes_all_epochs, start, end):
    plt.figure()
    plt.title("Relative change of every coordinate over epochs")
    for i in range(start, end):
        plt.plot(epoch_list, rel_changes_all_epochs[:, i], label=f"{i}th Latent Vector coordinate")
    plt.legend()
    plt.show()


def main(finger_index=DEFAULT_FINGER_INDEX, max_epoch=482):
    """
    Track the output of the MeshEncoder across 13 epochs and generate statistics and plots.

    Args:
        finger_index (int): Index of the finger for which data will be processed.
    """
    vertices_tensor_np = read_pickle(LOAD_DIR, "vertices_tensor", finger_index)[:-1]
    vertices_tensor = torch.tensor(vertices_tensor_np, dtype=torch.float32)  # Convert to PyTorch tensor

    input_dim = vertices_tensor.shape[1] * vertices_tensor.shape[2]  # num_vertices * 3
    mesh_encoder = MeshEncoder(input_dim=input_dim, latent_dim=LATENT_DIM)
    sdf_calculator = SDFCalculator(latent_dim=LATENT_DIM)
    training_context = TrainingContext(mesh_encoder, sdf_calculator, finger_index, len(vertices_tensor), 0.1, 0.01)

    mean_rel_change = []
    max_rel_change = []
    order_all = []
    order_rel_changes_all_epochs = []
    rel_changes_all_epochs = []
    # Iterate through 13 epochs
    epoch_list = list(range(2, EPOCH_WHERE_SAVE_ALL))
    # Add the sequence 12, 22, ..., 592
    epoch_list.extend(range(52, max_epoch + 1, 10))

    for epoch_index in epoch_list:
        print(f"\nProcessing Epoch {epoch_index}...\n")

        # Load MeshEncoder weights for the current epoch
        training_context.load_model_weights(epoch_index, time_index=0, debug=(DEBUG_ >= 2))

        # Compute latent vector statistics
        latent_vectors_tp, order, change_rel, change_rel_ordered = compute_latent_vector_stats(
            training_context.mesh_encoder, vertices_tensor
        )
        print(f"epoch: {epoch_index:03d} | order = {order}")
        mean_rel_change.append(np.mean(change_rel))
        max_rel_change.append(change_rel_ordered[0])

        order_rel_changes_all_epochs.append(change_rel_ordered)
        rel_changes_all_epochs.append(change_rel)
        order_all.append(order)

        if epoch_index == epoch_list[-1]:
            # Plot latent vector statistics for the current epoch
            plot_latent_vector_stats(latent_vectors_tp, order, change_rel, change_rel_ordered, epoch_index)

            latent_vectors = latent_vectors_tp.T
            cos_sim = np.zeros(len(latent_vectors))
            latent1 = latent_vectors[0]
            print(np.shape(latent1))
            for i in range(len(latent_vectors)):
                latent2 = latent_vectors[i]
                dot_product = np.dot(latent1, latent2)
                norm_latent1 = np.linalg.norm(latent1)
                norm_latent2 = np.linalg.norm(latent2)
                cos_sim[i] = dot_product / (norm_latent1 * norm_latent2)

            plt.figure()
            plt.title("Cosine Similarity over time")
            plt.grid()
            plt.ylabel(r"$\frac{q[i] \cdot q[0]}{\|q[i]\| \cdot \|q[0]\|}$")
            plt.plot(cos_sim, ".b", ms=5)
            plt.plot(cos_sim, "-", color="orange", linewidth=1)
            plt.show()

    rel_changes_all_epochs = np.array(rel_changes_all_epochs)
    order_rel_changes_all_epochs = np.array(order_rel_changes_all_epochs)
    order_all = np.array(order_all)
    print("\nSHOWING ORDER ALL\n")
    show_numpy_array_table(order_all)
    mean_order = find_mean_order(order_all)
    print(f"np.shape(mean_order) = {np.shape(mean_order)}")
    print(f"mean_order = {mean_order}")

    mean_rel_change = np.array(mean_rel_change)
    max_rel_change = np.array(max_rel_change)

    plot_relative_change_all_epochs(order_rel_changes_all_epochs, num_coords=5, epochs=epoch_list, start=0, end=50, ordered=True)
    plot_relative_change_all_epochs(order_rel_changes_all_epochs, num_coords=5, epochs=epoch_list, start=50, end=200, ordered=True)
    plot_relative_change_all_epochs(order_rel_changes_all_epochs, num_coords=5, epochs=epoch_list, start=200, end=max_epoch, ordered=True)
    plot_relative_change_all_epochs(rel_changes_all_epochs, num_coords=32, epochs=epoch_list, start=200, end=max_epoch, ordered=False)

    track_latent_rel_change_over_epoch(epoch_list, rel_changes_all_epochs, 0, 5)
    track_latent_rel_change_over_epoch(epoch_list, rel_changes_all_epochs, 5, 10)
    track_latent_rel_change_over_epoch(epoch_list, rel_changes_all_epochs, 15, 20)
    track_latent_rel_change_over_epoch(epoch_list, rel_changes_all_epochs, 20, 25)
    track_latent_rel_change_over_epoch(epoch_list, rel_changes_all_epochs, 25, 32)

    plt.figure()
    plt.title("relative change as a function of epoch")
    plt.xlabel("epoch")
    plt.ylabel("relative change ")
    plt.grid()
    plt.plot(mean_rel_change, label="mean")
    plt.plot(max_rel_change, label="max")
    plt.legend()
    plt.show()

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="use a trained model to recreate shapes")
    # Arguments for epoch and time indices
    parser.add_argument("--finger_index", type=int, default=730, help="Specify the finger index where the force was applied")
    parser.add_argument("--max_epoch", type=int, default=1000, help="Specify the finger index where the force was applied")
    args = parser.parse_args()

    ret = main(args.finger_index, args.max_epoch)
    exit(ret)
