# Blender: import and play an Uthana export

The shortest path from a generated motion to a playing character in Blender is to export the motion **on the character you want, with its mesh**, and import that file unchanged. Uthana has already retargeted the animation to that character's skeleton and proportions. You do not need to transfer animation, rebuild transforms, or fix axes.

Checked with Blender 5.0.1 and its built-in glTF and FBX importers.

## 1. Generate

Generate with any tool (`generate_motion`, `generate_motion_v2`, `generate_locomotion`, video-to-motion) and keep the returned motion ID. Review it with `get_preview` / `get_preview_frame` first if you want.

## 2. Export with the mesh

Call `download_motion` with the target character and `include_mesh=true` (the default):

```json
{
  "request_id": "walk-on-tar-glb",
  "motion_id": "<motion id>",
  "character_id": "cXi2eAP19XwQ",
  "format": "glb",
  "fps": 30,
  "include_mesh": true
}
```

GLB is the simplest choice for Blender. FBX also works. Export every clip you plan to combine on the **same character** at the **same fps**.

Skeleton-only exports (`include_mesh=false`) are for retargeting the clip onto your own copy of the same rig. Imported on their own, they show a bare armature, or in some tools only animated empties, with nothing to look at. Moving that animation onto a different mesh means extra work and is a common source of mistakes. Prefer a mesh export unless you specifically need the skeleton only.

## 3. Import and play

Set the scene frame rate **before** importing. Blender's glTF importer converts keyframe times to the scene rate, and the default scene is 24 fps. A 30 fps clip imported into a 24 fps scene still plays at the right speed, but its frame count changes (53 frames become 42), which confuses frame-based checks.

```python
import bpy

bpy.context.scene.render.fps = 30          # match the export fps
bpy.ops.import_scene.gltf(filepath="walk.glb")   # FBX: bpy.ops.wm.fbx_import(filepath="walk.fbx")

arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
start, end = (int(f) for f in arm.animation_data.action.frame_range)
bpy.context.scene.frame_start, bpy.context.scene.frame_end = start, end
```

Press Play. The character mesh is skinned to the armature, and the armature carries the action. Blender's glTF importer also adds an `Icosphere` object as the bones' display shape. It is not part of the exported file; leave it alone or hide it, and exclude it from measurements. GLB actions start at frame 0 and FBX actions at frame 1. The FBX importer brings the character in at real-world size, but with a non-unit object scale on the armature. Apply scale (Ctrl+A → Scale) only if another tool needs scale 1.

## 4. Several clips on one character

Clips exported on the same character share the same armature and bone names. Import the first clip as the character. For each further clip, import it, keep its action, and delete its duplicate objects:

```python
import bpy

def add_clip(arm, path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    other = next(o for o in new if o.type == "ARMATURE")
    action = other.animation_data.action
    action.name = name
    action.use_fake_user = True            # keep it after its armature is deleted
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    return action

bpy.context.scene.render.fps = 30
bpy.ops.import_scene.gltf(filepath="walk_forward.glb")
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
arm.animation_data.action.name = "walk_forward"
strafe = add_clip(arm, "walk_right.glb", "walk_right")

arm.animation_data.action = strafe         # switch clips
if arm.animation_data.action_slot is None and strafe.slots:   # Blender 4.4+ slotted actions
    arm.animation_data.action_slot = strafe.slots[0]
```

Switch clips by assigning a different action, or lay them out as NLA strips. No retargeting or transform rebuild is needed.

## Directions and axes

- **Uthana directions are character-relative.** Locomotion `travel_angle` is 0 forward, 90 to the character's right, -90 to its left, 180 backward. Stitch placement uses `forward_m`, `right_m` and `turn_degrees` (positive to the right) relative to the preceding clip's ending facing.
- **GLB** follows glTF: Y-up, with the character facing +Z and its left side toward +X.
- **In Blender** (Z-up), both GLB and FBX imports face **-Y**, with the character's left toward **+X**.
- **Check direction against the character, not the world.** Compare root travel with the facing at the first frame, for example up crossed with the vector from `upperarm_l` to `upperarm_r` (in Blender: +Z × −X = −Y, the character's forward). Mirrored labels usually come from comparing against world axes.

## Checks worth running

- **Floor.** In rest pose the mesh's lowest point should sit at z ≈ 0. Measure the evaluated mesh per frame to find foot or toe penetration. Measure only meshes with an Armature modifier, so the importer's `Icosphere` bone shape is excluded.
- **Loop seam.** For a loop, compare each joint's rotation on the first and last frame. A few degrees is normal; much more can show a hitch.
- **Root travel.** Measure the first-to-last pelvis displacement on the ground plane, with distance and direction relative to the starting facing.
