import numpy as np
from PIL import Image, ImageEnhance
import os
from tqdm import tqdm
import cv2
import random
import argparse
import imageio

def images_to_video(input_folder, output_video, fps=30, max_width=1920, max_height=1080):
    # Get all PNG images from the input folder and sort by filename (assumed to be frame numbers)
    images = [img for img in os.listdir(input_folder) if img.endswith(".png")]
    images.sort(key=lambda x: int(os.path.splitext(x)[0]))

    if not images:
        print("No images found in the folder.")
        return

    frames = [imageio.imread(os.path.join(input_folder, img)) for img in images]
    imageio.mimwrite(output_video, frames, fps=fps)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    # Video and output directory parameters
    parser.add_argument("--video_path", type=str, required=False, 
                        default="",
                        help="Path to input images")
    parser.add_argument("--output_dir", type=str, required=False, 
                        default="",
                        help="Output directory")
    parser.add_argument("--level", choices=['default', 'small', 'middle', 'large'], default='large',
                        help="Mask level")
    # New parameter to choose visualization mode
    parser.add_argument("--vis_mode", type=str, choices=["full", "seperate", "both"], default="full",
                        help="Visualization mode: full (full-mask), seperate (separate masks per uid), both (generate both)")
    args = parser.parse_args()

    level = args.level
    basedir = args.output_dir
    npybasedir = os.path.join(basedir, level, 'final-output')
    imagebasedir = args.video_path

    # Load image and npy file lists
    image_name_list = os.listdir(imagebasedir)
    image_name_list.sort(key=lambda p: int(os.path.splitext(p)[0]))

    npy_name_list = []
    for name in os.listdir(npybasedir):
        if 'npy' in name:
            npy_name_list.append(name)
    npy_name_list.sort()
    print("Numpy files:", npy_name_list)
    npy_list = [np.load(os.path.join(npybasedir, name)) for name in npy_name_list]
    image_list = [Image.open(os.path.join(imagebasedir, name)) for name in image_name_list]
    assert len(npy_list) == len(image_name_list)
    print("Number of frames:", len(npy_list))

    # Create uid directories for separate visualization
    uid_dirs = {}
    for uid in range(npy_list[0].shape[0]):
        uid_dir = os.path.join(basedir, level, 'visualization', 'seperate', f"uid_{uid}")
        os.makedirs(uid_dir, exist_ok=True)
        uid_dirs[uid] = uid_dir

    # Separate visualization: generate per-uid visualization and combined image per frame
    if args.vis_mode in ["seperate", "both"]:
        print("Generating separate visualization...")
        # Loop over frames
        for frame_id, (masks, image) in tqdm(enumerate(zip(npy_list, image_list)), total=len(npy_list)):
            # Darken the original image for background
            dark_image = ImageEnhance.Brightness(image).enhance(0.3)
            dark_image_array = np.array(dark_image)
            highlighted_images = []
            mask_images = []
            # Process each uid mask
            for uid in range(masks.shape[0]):
                current_mask = masks[uid][0]  # assuming first channel is used
                image_array = np.array(image)
                # Highlight current mask region by using the original image, others darkened
                highlighted_image_array = np.where(current_mask[:, :, np.newaxis], image_array, dark_image_array)
                highlighted_image = Image.fromarray(highlighted_image_array.astype('uint8'))
                # Create a binary mask image for visualization
                bool_mask_array = (current_mask * 255).astype(np.uint8)
                bool_mask_image = Image.fromarray(bool_mask_array).convert("RGB")
                # Create a combined image (original on top, mask below)
                uid_frame = Image.new('RGB', (image.width, image.height * 2))
                uid_frame.paste(highlighted_image, (0, 0))
                uid_frame.paste(bool_mask_image, (0, image.height))
                uid_frame.save(os.path.join(uid_dirs[uid], f"{frame_id:05}.png"))
                highlighted_images.append(highlighted_image)
                mask_images.append(bool_mask_image)
            # Combine all uid visualizations side by side
            total_width = image.width * len(highlighted_images)
            max_height = image.height * 2
            final_image = Image.new('RGB', (total_width, max_height))
            for i, img in enumerate(highlighted_images):
                final_image.paste(img, (i * image.width, 0))
            for i, img in enumerate(mask_images):
                final_image.paste(img, (i * image.width, image.height))
            combined_save_path = os.path.join(basedir, level, 'visualization', 'seperate', f"{frame_id:05}.png")
            final_image.save(combined_save_path)
        # Optionally, generate separate videos for each uid from the separate visualization
        output_video_dir = os.path.join(basedir, level, 'visualization', 'seperate', 'videos')
        os.makedirs(output_video_dir, exist_ok=True)
        for uid in tqdm(range(len(uid_dirs))):
            uid_folder = uid_dirs[uid]
            video_uid_path = os.path.join(output_video_dir, f"uid_{uid}.mp4")
            images_to_video(uid_folder, video_uid_path)

    # Full mask visualization: blend original image with all masks colored
    if args.vis_mode in ["full", "both"]:
        print("Generating full mask visualization...")
        savedir_full = os.path.join(basedir, level, 'visualization', 'full-mask-npy')
        video_path = os.path.join(basedir, level, 'visualization', f'full-mask-{level}.mp4')
        os.makedirs(savedir_full, exist_ok=True)

        # Define a helper function to generate random colors
        def generate_random_colors(num_colors):
            colors = []
            for _ in range(num_colors):
                color = tuple(random.randint(0, 255) for _ in range(3))
                colors.append(color)
            return colors

        num_masks = max(len(masks) for masks in npy_list)
        colors = generate_random_colors(num_masks)

        video_frames = []
        output_path_list = []
        for frame_id, (masks, image) in tqdm(enumerate(zip(npy_list, image_list)), total=len(npy_list)):
            image_np = np.array(image)
            mask_combined = np.zeros_like(image_np, dtype=np.uint8)
            # Overlay each mask with its corresponding random color
            for i, mask in enumerate(masks):
                color = colors[i % len(colors)]
                # Ensure the mask is binary (0 or 1)
                mask_binary = (mask[0] > 0).astype(np.uint8)
                for j in range(3):  # for each channel in RGB
                    mask_combined[:, :, j] += mask_binary * color[j]
            mask_combined = np.clip(mask_combined, 0, 255)
            # Blend the original image with the colored mask
            blended_image = cv2.addWeighted(image_np, 0.7, mask_combined, 0.3, 0)
            output_path = os.path.join(savedir_full, f"frame_{frame_id:04d}.png")
            output_path_list.append(output_path)
            Image.fromarray(blended_image).save(output_path)
        # Create video from generated images
        frames = [imageio.imread(img) for img in output_path_list]
        imageio.mimwrite(video_path, frames, fps=30)
        print(f"Video saved at {video_path}")


