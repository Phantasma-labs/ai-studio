"""
ui_core.py — Shared workflow UI for AI Studio.
Called by app.py (cloud) and applocal.py (local) with pre-configured engine settings.
"""
import streamlit as st
import json
import re
from datetime import datetime
import pipeline

# Attempt to catch specific 429 exceptions gracefully
try:
    from google.api_core.exceptions import ResourceExhausted
except ImportError:
    ResourceExhausted = Exception

def _parse_json_output(text):
    """Safely parse LLM output as JSON. Returns a list if successful, else the raw text."""
    try:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return text
    except Exception:
        return text

def _split_suggestions(text, count=3):
    """Split a block of text into N suggestions. Simple split by Option X or A/B/C."""
    if not text: return [""] * count
    # Look for markers like 'Option 1:', 'Option A:', etc.
    pattern = r'(Option\s+[0-9A-Z]:)'
    parts = re.split(pattern, text, flags=re.IGNORECASE)

    suggestions = []
    # parts[0] might be preamble.
    # parts[1] = "Option 1:", parts[2] = " content..."
    for i in range(1, len(parts), 2):
        label = parts[i].strip()
        content = parts[i+1].strip() if i+1 < len(parts) else ""
        suggestions.append(f"{label} {content}")

    if len(suggestions) < count:
        # Fallback: split by newlines or just return the whole thing
        return [text] + [""] * (count - 1)

    return suggestions[:count]


def _build_per_shot_md(final_prompts_text: str) -> str:
    """
    Convert the render artist output into a clearly structured markdown string
    with per-shot T2I and I2V sections labelled sh 01, sh 02, etc.
    Used for the MD download deliverable.
    """
    scenes = _parse_json_output(final_prompts_text)

    if isinstance(scenes, str):
        # Fallback if JSON parsing failed
        return scenes

    lines = []
    for i, scene in enumerate(scenes, 1):
        sh_label = f"sh {i:02d}"
        header = scene.get("scene_label", f"Scene {i}")
        t2i = scene.get("t2i", "")
        i2v = scene.get("i2v", "")

        lines.append(f"### {sh_label} — {header}\n")
        if t2i:
            lines.append(f"#### {sh_label} T2I (Text-to-Image)\n")
            lines.append(t2i + "\n")
        if i2v:
            lines.append(f"#### {sh_label} I2V (Image-to-Video)\n")
            lines.append(i2v + "\n")
        if not t2i and not i2v:
            lines.append(f"No output for {sh_label}\n")
        lines.append("---\n")

    return "\n".join(lines)


def render_prompt_blocks(output_text: str):
    """
    Parse render artist output and display T2I and I2V in separate
    st.code() boxes (with built-in copy button).
    Handles both single-scene (Product Shot) and multi-scene (Storytelling) output.
    """
    scenes = _parse_json_output(output_text)

    if isinstance(scenes, str):
        # Fallback — show raw output
        st.code(scenes, language="markdown")
        return

    # If we have a list of scenes, render them
    for scene in scenes:
        header = scene.get("scene_label", "Product Shot")
        st.markdown(f"#### 🎬 {header}")
        t2i = scene.get("t2i", "")
        i2v = scene.get("i2v", "")

        if t2i:
            st.caption("🖼 T2I Prompt — copy and paste into your image model")
            st.code(t2i, language="markdown")
        if i2v:
            st.caption("🎞 I2V Animation Prompt — copy and paste into your video model")
            st.code(i2v, language="markdown")
        if not t2i and not i2v:
            st.code("No prompt generated.", language="markdown")
        st.divider()


def init_session_state():
    session_vars = [
        "phase", "story_arc", "screenplay", "art_suggestions", "camera_suggestions",
        "generation_seed", "concept_input", "art_input", "camera_input",
        "final_art_pref", "final_cam_pref", "final_prompts", "storyboard_prompt",
        "last_seed", "product_shot_output", "preview_image_bytes", "last_uploaded_image",
        "refining_art", "refining_cam"
    ]
    for var in session_vars:
        if var not in st.session_state:
            st.session_state[var] = (
                0 if var in ["phase", "last_seed"]
                else (1 if var == "generation_seed"
                      else (False if var in ["refining_art", "refining_cam"]
                            else ("" if var not in ["preview_image_bytes", "last_uploaded_image"]
                                    else None)))
            )
    return session_vars


def reset_state(session_vars):
    for key in session_vars:
        if key in st.session_state:
            st.session_state[key] = (
                0 if key in ["phase", "last_seed"]
                else (1 if key == "generation_seed"
                      else ("" if key not in ["preview_image_bytes", "last_uploaded_image"]
                            else None))
            )


def render_concept_sidebar(engine_mode, api_key):
    """Image upload + concept text area."""
    st.sidebar.divider()
    st.sidebar.subheader("Concept Initialization")

    uploaded_image = st.sidebar.file_uploader(
        "Upload an Image Concept (Optional):", type=["jpg", "jpeg", "png"]
    )
    if uploaded_image is not None and st.session_state.get("last_uploaded_image") != uploaded_image.file_id:
        with st.spinner("Agents are analyzing image concept..."):
            try:
                caption = pipeline.describe_image(
                    uploaded_image.getvalue(),
                    engine_mode=engine_mode,
                    api_key=api_key,
                    mime_type=uploaded_image.type
                )
                st.session_state.concept_input = caption
                st.session_state.last_uploaded_image = uploaded_image.file_id
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Image analysis failed: {e}")

    st.sidebar.text_area(
        "Enter your concept:",
        key="concept_input",
        placeholder="A cyberpunk detective chases a rogue android through neon-lit streets..."
    )


def render_product_shot(engine_mode, model_name, api_key):
    """Product Shot workflow UI."""
    st.markdown("### 📸 Product Shot")
    st.info("Generates a single, hyper-detailed product shot — T2I prompt + I2V animation instruction.")
    st.info("👈 Enter your concept in the sidebar to begin.")

    if st.sidebar.button("Generate Product Shot"):
        if not st.session_state.concept_input:
            st.sidebar.warning("Please enter a concept first.")
        else:
            with st.spinner(f"Agents are synthesizing product shot using {model_name}..."):
                try:
                    out = pipeline.run_product_shot_mode(
                        st.session_state.concept_input,
                        engine_mode=engine_mode,
                        model_name=model_name,
                        api_key=api_key
                    )
                    st.session_state.product_shot_output = out
                    st.session_state.preview_image_bytes = None
                    if engine_mode == "Local":
                        pipeline.unload_ollama_model(model_name)
                        st.info("🧹 VRAM cleared — GPU is ready for ComfyUI rendering.")
                except Exception as e:
                    st.error(f"Error during execution: {e}")

    if st.session_state.product_shot_output:
        st.success("Product Shot synthesis complete.")
        st.markdown("### 🍌 Nano Banana Pro Rendering Prompt")
        render_prompt_blocks(st.session_state.product_shot_output)

        extracted_prompt = st.session_state.product_shot_output

        col_img1, col_img2 = st.columns(2)
        with col_img1:
            if st.button("Generate Local Image (ComfyUI)"):
                with st.spinner("Dispatching to Local ComfyUI..."):
                    try:
                        img_bytes = pipeline.generate_image_comfyui(extracted_prompt)
                        st.session_state.preview_image_bytes = img_bytes
                        st.success("Successfully generated by ComfyUI!")
                    except Exception as e:
                        st.error(str(e))

        with col_img2:
            if st.session_state.preview_image_bytes:
                st.image(st.session_state.preview_image_bytes, caption="Generated Preview")
                st.download_button(
                    label="📥 Download Preview Image",
                    data=st.session_state.preview_image_bytes,
                    file_name="product_shot_preview.jpg",
                    mime="image/jpeg"
                )

        st.markdown("### 📦 Deliverables")
        slug = re.sub(r'[^a-zA-Z0-9\s]', '', st.session_state.concept_input)
        slug = "_".join(slug.split()[:3]).lower() or "product_shot"
        date_str = datetime.now().strftime("%Y%m%d")
        md_content = f"# Product Shot Prompt\n\n{st.session_state.product_shot_output}"
        st.download_button(
            label="📥 Download Output (.md)",
            data=md_content,
            file_name=f"{date_str}_{slug}.md",
            mime="text/markdown"
        )


def render_storytelling(engine_mode, model_name, api_key):
    """Storytelling multi-phase workflow UI."""
    st.markdown("### 🎥 Storytelling Workflow")
    st.info("Guides you through a 3-phase creative process from narrative conceptualization to a multi-shot storyboard script.")
    st.info("👈 Enter your concept in the sidebar to begin.")

    if st.sidebar.button("Generate Script"):
        if not st.session_state.concept_input:
            st.sidebar.warning("Please enter a concept first.")
        else:
            with st.spinner(f"Agents are writing using {model_name}..."):
                try:
                    arc, script, art_suggs = pipeline.run_phase_1(
                        st.session_state.concept_input,
                        engine_mode=engine_mode,
                        model_name=model_name,
                        api_key=api_key
                    )
                    st.session_state.story_arc = arc
                    st.session_state.screenplay = script
                    st.session_state.art_suggestions = art_suggs
                    st.session_state.phase = 1
                except Exception as e:
                    st.sidebar.error(f"Error during Phase 1: {e}")

    # Phase 1.5 sidebar
    if st.session_state.phase >= 1:
        st.sidebar.divider()
        st.sidebar.subheader("Phase 1.5: Art Direction")

        art_suggestions = _split_suggestions(st.session_state.art_suggestions)
        art_options = [f"Option {i+1}" for i in range(len(art_suggestions))] + ["Custom"]

        art_choice = st.sidebar.radio(
            "Select Art Base:",
            art_options,
            disabled=(st.session_state.phase >= 2)
        )

        # Determine base text
        default_art_text = ""
        if art_choice != "Custom" and art_suggestions:
            idx = art_options.index(art_choice)
            default_art_text = art_suggestions[idx]

        if st.sidebar.button("✏️ Refine Art Details", disabled=(st.session_state.phase >= 2)):
            st.session_state.refining_art = True
            st.session_state.art_input = default_art_text
            st.rerun()

        if st.session_state.phase == 1:
            if st.sidebar.button("Confirm Art & Generate Camera Options"):
                # Use current art_input if refining, else the choice
                final_art_pref = st.session_state.art_input if st.session_state.refining_art else default_art_text
                st.session_state.final_art_pref = final_art_pref
                with st.spinner(f"Camera Consultant is working using {model_name}..."):
                    try:
                        cam_suggs = pipeline.run_phase_1_5(
                            st.session_state.screenplay,
                            st.session_state.final_art_pref,
                            engine_mode=engine_mode,
                            model_name=model_name,
                            api_key=api_key
                        )
                        st.session_state.camera_suggestions = cam_suggs
                        st.session_state.phase = 2
                        st.session_state.refining_art = False
                    except Exception as e:
                        st.sidebar.error(f"Error during Phase 1.5: {e}")

    # Phase 2 sidebar
    if st.session_state.phase >= 2:
        st.sidebar.divider()
        st.sidebar.subheader("Phase 2: Cinematography")

        cam_suggestions = _split_suggestions(st.session_state.camera_suggestions)
        cam_options = [f"Option {i+1}" for i in range(len(cam_suggestions))] + ["Custom"]

        cam_choice = st.sidebar.radio(
            "Select Camera Base:",
            cam_options,
            disabled=(st.session_state.phase >= 3)
        )

        # Determine base text
        default_cam_text = ""
        if cam_choice != "Custom" and cam_suggestions:
            idx = cam_options.index(cam_choice)
            default_cam_text = cam_suggestions[idx]

        if st.sidebar.button("✏️ Refine Camera Details", disabled=(st.session_state.phase >= 3)):
            st.session_state.refining_cam = True
            st.session_state.camera_input = default_cam_text
            st.rerun()

        if st.session_state.phase == 2:
            if st.sidebar.button("Generate Final Prompts"):
                # Use current input if refining, else the choice
                final_cam_pref = st.session_state.camera_input if st.session_state.refining_cam else default_cam_text
                st.session_state.final_cam_pref = final_cam_pref
                st.session_state.phase = 3
                st.session_state.refining_cam = False

    # --- Main panel ---
    if st.session_state.refining_art:
        st.subheader("🎨 Refine Art Direction")
        st.info("You are editing the Art Direction. This will be used as the base for cinematography suggestions.")
        refined_art = st.text_area(
            "Art Direction Details:",
            value=st.session_state.art_input,
            height=300,
            help="Provide detailed visual descriptions: materials, colors, lighting, and atmosphere."
        )
        st.session_state.art_input = refined_art
        if st.button("Save Art Direction"):
            st.session_state.refining_art = False
            st.rerun()
        st.divider()

    elif st.session_state.refining_cam:
        st.subheader("🎥 Refine Cinematography")
        st.info("You are editing the Cinematography. This will be used by the Render Artist to finalize the shots.")
        refined_cam = st.text_area(
            "Cinematography Details:",
            value=st.session_state.camera_input,
            height=300,
            help="Provide detailed camera instructions: movement, lens, focal length, and timing."
        )
        st.session_state.camera_input = refined_cam
        if st.button("Save Cinematography"):
            st.session_state.refining_cam = False
            st.rerun()
        st.divider()

    if st.session_state.phase == 1:
        st.subheader("Phase 1: Pre-Production Review")
        col1, col2 = st.columns(2)
        with col1:
            with st.expander("📝 Story Arc", expanded=True):
                st.write(st.session_state.story_arc)
            with st.expander("🎬 Screenplay", expanded=True):
                st.write(st.session_state.screenplay)
        with col2:
            with st.expander("💡 Art Director Suggestions", expanded=True):
                st.write(st.session_state.art_suggestions)

    elif st.session_state.phase == 2:
        st.subheader("Phase 1.5: Cinematography Review")
        col1, col2 = st.columns(2)
        with col1:
            with st.expander("View Screenplay"):
                st.write(st.session_state.screenplay)
            with st.expander("🎨 Chosen Art Direction", expanded=True):
                st.write(st.session_state.final_art_pref)
        with col2:
            with st.expander("🎥 Cinematographer Suggestions", expanded=True):
                st.write(st.session_state.camera_suggestions)

    elif st.session_state.phase == 3:
        st.subheader("Phase 2: Production (Finalizing Prompts)")

        with st.spinner(f"Render Artist is working... (Seed: {st.session_state.generation_seed})"):
            try:
                if st.session_state.last_seed != st.session_state.generation_seed:
                    seeded_screenplay = (
                        st.session_state.screenplay
                        + f"\n[Variant {st.session_state.generation_seed}]"
                    )
                    r_prompts, s_prompt = pipeline.run_phase_2(
                        seeded_screenplay,
                        st.session_state.final_art_pref,
                        st.session_state.final_cam_pref,
                        engine_mode=engine_mode,
                        model_name=model_name,
                        api_key=api_key
                    )
                    st.session_state.final_prompts = r_prompts
                    st.session_state.storyboard_prompt = s_prompt
                    st.session_state.last_seed = st.session_state.generation_seed
                    st.session_state.preview_image_bytes = None
                    if engine_mode == "Local":
                        pipeline.unload_ollama_model(model_name)
                        st.info("🧹 VRAM cleared — GPU is ready for ComfyUI rendering.")

                st.success(f"Workflow Complete! (Variant {st.session_state.generation_seed})")

                st.markdown("### 🍌 Nano Banana Pro Rendering Prompts")
                formatted_prompts = st.session_state.final_prompts
                render_prompt_blocks(formatted_prompts)

                st.markdown("### 🖼️ Storyboard Consolidation Prompt")
                st.code(st.session_state.storyboard_prompt, language="markdown")

                col_img1, col_img2 = st.columns(2)
                with col_img1:
                    if st.button("Generate Local Image (ComfyUI)"):
                        with st.spinner("Dispatching Storyboard to Local ComfyUI..."):
                            try:
                                img_bytes = pipeline.generate_image_comfyui(
                                    st.session_state.storyboard_prompt
                                )
                                st.session_state.preview_image_bytes = img_bytes
                                st.success("Successfully generated by ComfyUI!")
                            except Exception as e:
                                st.error(str(e))

                with col_img2:
                    if st.session_state.preview_image_bytes:
                        st.image(st.session_state.preview_image_bytes, caption="Generated Storyboard")
                        st.download_button(
                            label="📥 Download Storyboard Image",
                            data=st.session_state.preview_image_bytes,
                            file_name="storyboard_preview.jpg",
                            mime="image/jpeg"
                        )

                st.markdown("### 📦 Deliverables")
                slug = re.sub(r'[^a-zA-Z0-9\s]', '', st.session_state.concept_input)
                slug = "_".join(slug.split()[:3]).lower() or "story"
                date_str = datetime.now().strftime("%Y%m%d")
                per_shot_md = _build_per_shot_md(formatted_prompts)
                md_content = (
                    f"# Original Concept\n\n{st.session_state.concept_input}\n\n"
                    f"# Phase 1: Pre-Production\n\n"
                    f"## Story Arc\n\n{st.session_state.story_arc}\n\n"
                    f"## Screenplay\n\n{st.session_state.screenplay}\n\n"
                    f"## Art Director Suggestions\n\n{st.session_state.art_suggestions}\n\n"
                    f"## Chosen Art Direction\n\n{st.session_state.final_art_pref}\n\n"
                    f"# Phase 1.5: Cinematography\n\n"
                    f"## Cinematographer Suggestions\n\n{st.session_state.camera_suggestions}\n\n"
                    f"## Chosen Cinematography\n\n{st.session_state.final_cam_pref}\n\n"
                    f"# Phase 2: Production\n\n"
                    f"## Per-Shot Rendering Prompts\n\n{per_shot_md}\n\n"
                    f"## Consolidated Storyboard Prompt\n\n{st.session_state.storyboard_prompt}"
                )
                st.download_button(
                    label="📥 Download Full Package (.md)",
                    data=md_content,
                    file_name=f"{date_str}_{slug}_Complete.md",
                    mime="text/markdown"
                )

            except Exception as e:
                st.error(f"Error during Phase 2: {e}")


def render_reset_controls(session_vars, workflow_mode):
    """Reset + seed controls at the bottom of the sidebar."""
    st.sidebar.divider()
    reset_disabled = st.session_state.phase == 0 and not st.session_state.product_shot_output
    if st.sidebar.button("Start Another Run (Reset)", disabled=reset_disabled):
        st.session_state.clear()
        import streamlit.components.v1 as components
        components.html("<script>window.parent.location.reload();</script>", height=0)

    if workflow_mode == "Storytelling" and st.session_state.phase == 3:
        if st.sidebar.button("Generate from another seed"):
            st.session_state.generation_seed += 1
            st.rerun()


def run(engine_mode: str, model_name: str, api_key, workflow_mode: str):
    """
    Main entry point called by app.py and applocal.py.
    engine_mode: 'Cloud' or 'Local'
    model_name: resolved model string
    api_key: Google API key (None for local)
    workflow_mode: 'Storytelling' or 'Product Shot'
    """
    session_vars = init_session_state()
    render_concept_sidebar(engine_mode, api_key)

    if workflow_mode == "Product Shot":
        render_product_shot(engine_mode, model_name, api_key)
    else:
        render_storytelling(engine_mode, model_name, api_key)

    render_reset_controls(session_vars, workflow_mode)
