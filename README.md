# ComfyUI Bird Cage

A ComfyUI custom-node package that turns a starting image into an interactive, AI-refinable 2.5D scene served from the same ComfyUI server at **`/bird-cage/`**.

The motivating example is a cloth-covered bird cage on a table: segment the cloth, generate or provide the hidden/revealed state, then click-drag the cloth in real time to uncover the scene. Browser-side mesh deformation keeps interaction responsive; an optional image-edit workflow such as FLUX.2 Klein can refine the flattened result after dragging stops.

## Features

- Standalone UI at `/bird-cage/` with no npm build or CDN dependency.
- Source/revealed-image upload plus built-in manual cloth-mask painting.
- Optional text-guided segmentation through any compatible ComfyUI API workflow.
- Generic workflow profiles for **segment**, **reveal**, **cleanup**, and **refine** stages.
- Import ComfyUI **Save (API Format)** JSON and bind Bird Cage semantic controls to arbitrary node inputs.
- Tunable prompts, steps, CFG/guidance, sampler, scheduler, seed, denoise, checkpoint/diffusion model, VAE, text encoder, and four LoRA slots.
- Full-frame revealed plate protected outside the cloth mask to reduce model drift.
- Canvas cloth mesh for immediate click-drag interaction.
- Refine-on-idle: current frame + changed-region mask + revealed plate can be sent to a Klein/image-edit workflow.
- Regular ComfyUI nodes: **Bird Cage: Build Scene Layers** and **Bird Cage: Load Session**.

## Install

```bash
cd /workspace/ComfyUI/custom_nodes
git clone git@github-runpod:showads/ComfyUI-Birdcage.git
```

Restart ComfyUI, then open the same host/port you use for ComfyUI with `/bird-cage/`, for example:

```text
http://127.0.0.1:8188/bird-cage/
```

There are no additional Python dependencies beyond packages ComfyUI already provides (`aiohttp`, Pillow, NumPy, Torch).

## RunPod SSH setup for multiple GitHub repos

If your RunPod machine will pull several custom-node repositories from the same GitHub account, **do not use a deploy key**. GitHub deploy keys are scoped to one repository.

Instead, create one dedicated machine SSH key on the persistent RunPod volume and add its public key to the GitHub account under **Settings → SSH and GPG keys**.

Generate it once:

```bash
mkdir -p /workspace/.ssh
chmod 700 /workspace/.ssh

ssh-keygen -t ed25519 \
  -C "runpod-comfyui" \
  -f /workspace/.ssh/github_ed25519 \
  -N ""

cat /workspace/.ssh/github_ed25519.pub
```

Add the printed public key to GitHub, then create an SSH alias on the pod:

```bash
cat > /workspace/.ssh/config <<'EOF'
Host github-runpod
  HostName github.com
  User git
  IdentityFile /workspace/.ssh/github_ed25519
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF

chmod 600 /workspace/.ssh/config
```

Test it:

```bash
ssh -T github-runpod
```

GitHub normally answers that authentication succeeded but shell access is not provided.

Clone this node:

```bash
cd /workspace/ComfyUI/custom_nodes
git clone git@github-runpod:showads/ComfyUI-Birdcage.git
```

Clone additional repos using the same host alias:

```bash
git clone git@github-runpod:showads/Another-ComfyUI-Node.git
```

Update later with:

```bash
git -C /workspace/ComfyUI/custom_nodes/ComfyUI-Birdcage pull --ff-only
```

### Security note

An account-level SSH key has the same Git repository access as that GitHub user. If the account has unrelated sensitive private repositories, the more isolated setup is a dedicated GitHub **machine-user account** invited only to the custom-node repos you want RunPod to access. If the GitHub account is primarily for these repos, one account-level RunPod key is a reasonable setup.

Never commit `/workspace/.ssh/github_ed25519`, bake it into an image, or copy it into a public pod template.

## How Bird Cage represents a scene

The scene is deliberately simple:

```text
revealed plate
    ↑
RGBA cloth crop on a deformable triangle mesh
    ↑
pointer interaction
```

The revealed plate uses the source image outside the cloth mask and the generated revealed image inside the mask. This protects unrelated parts of the scene from generation drift.

The browser deforms only the cloth layer, so dragging can run at display frame rate without doing diffusion inference for every pointer event.

## First run

1. Open `/bird-cage/` and create a scene.
2. Upload the starting image.
3. Provide the cloth mask by either painting it in the Scene tab, uploading a mask, or choosing a segmentation workflow profile.
4. Upload a revealed-state image or configure a Reveal workflow profile.
5. Click **Compile interactive scene**.
6. Drag the cloth directly on the canvas.
7. Optionally configure a Refine workflow and enable refine-after-drag.

## Workflow profiles

ComfyUI's editor workflow JSON and API prompt JSON are different. Bird Cage executes **API-format** workflows because that is the representation ComfyUI's execution queue consumes.

In ComfyUI, export the graph you want using **Save (API Format)**. In Bird Cage's **Workflows** tab:

1. Select `Segment`, `Reveal`, `Cleanup`, or `Refine`.
2. Import the API-format JSON.
3. Bird Cage inspects literal node inputs.
4. Bind semantic controls to the relevant node inputs.
5. Select the node that exposes the final image, usually `PreviewImage` or `SaveImage`, or leave it on auto-detect.

Example mappings:

```text
source_image    → LoadImage.image
mask_image      → LoadImage.image
reference_image → LoadImage.image
prompt          → CLIPTextEncode.text
negative_prompt → CLIPTextEncode.text
steps           → sampler.steps
sampler         → sampler.sampler_name
scheduler       → sampler.scheduler
seed            → sampler.seed
denoise         → sampler.denoise
lora_1_name     → LoraLoader.lora_name
```

Because the mappings are semantic rather than tied to node class names, the app can work with core loaders, GGUF/custom loaders, alternate sampler nodes, and different model families without Bird Cage knowing their graph topology.

## Segmentation

Bird Cage intentionally does not hard-depend on one SAM/GroundingDINO node pack because several incompatible ComfyUI implementations exist.

A text-guided segmentation workflow can bind:

- `source_image`
- `detector_prompt` or `prompt`
- `box_threshold`
- `text_threshold`

and expose a mask-looking image through an output node. Bird Cage thresholds/expands/feathers that output into the cloth mask.

The built-in brush mask is also useful for correcting an AI-generated mask.

## LoRAs

The UI exposes four LoRA slots per generation stage. Each slot has file name, model strength, and CLIP strength. Build those loader slots into the underlying ComfyUI workflow, then bind their inputs in the profile editor.

Bird Cage does not dynamically rewrite arbitrary graph topology; using explicit LoRA slots is much more reliable across custom node implementations.

## Klein/image-edit refine

Refinement is intentionally outside the real-time interaction loop:

```text
pointer drag
   ↓
local cloth mesh at frame rate
   ↓
drag stops / idle debounce
   ↓
flatten current frame
+ generate changed-region mask
+ provide revealed plate as optional reference
   ↓
ComfyUI refine workflow
   ↓
refined snapshot preview
```

A useful refine prompt is:

> Preserve the scene and composition. Make the displaced fabric, folds, occlusion, contact shadows, and newly revealed area physically realistic. Do not change unrelated areas.

Bird Cage provides three semantic image inputs to a refine profile:

- `source_image`: current flattened interactive frame
- `mask_image`: changed region covering the original and displaced cloth
- `reference_image`: compiled revealed plate

Bind whichever ones your Klein/image-edit workflow supports. The backend composites the refine result back through the changed-region mask to protect unrelated pixels even if the underlying workflow ignores the mask.

## Data

Sessions and workflow profiles default to:

```text
ComfyUI/output/bird-cage/
```

Set `BIRDCAGE_DATA_DIR` to override it.

When Bird Cage executes a workflow, its temporary workflow inputs are copied under:

```text
ComfyUI/input/bird-cage/<session-id>/
```

so ordinary `LoadImage` nodes can consume them.

## Main routes

```text
GET    /bird-cage/
GET    /bird-cage/api/config
GET    /bird-cage/api/sessions
POST   /bird-cage/api/session
GET    /bird-cage/api/session/{id}
POST   /bird-cage/api/session/{id}/upload
POST   /bird-cage/api/session/{id}/manual-mask
POST   /bird-cage/api/session/{id}/compile
POST   /bird-cage/api/session/{id}/refine
GET    /bird-cage/api/session/{id}/asset/{name}
GET    /bird-cage/api/workflows
POST   /bird-cage/api/workflows/inspect
POST   /bird-cage/api/workflows
DELETE /bird-cage/api/workflows/{stage}/{name}
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Security

Bird Cage inherits the security model of the ComfyUI server it is loaded into, and imported workflow profiles can submit arbitrary ComfyUI workflows to that instance. Do not expose an unrestricted ComfyUI + Bird Cage server directly to untrusted users without authentication/network controls.

## License

MIT
