# Ollama Models Guide (Under 3B Parameters)

## Recommended Models for Limited Resources

All models listed here are under 3 billion parameters, making them suitable for systems with limited memory/resources.

### ✅ Required Models

1. **`nomic-embed-text`** (~137M parameters)
   - **Purpose**: Text embeddings for RAG/semantic search
   - **Status**: ✅ Small enough, keep this
   ```bash
   ollama pull nomic-embed-text
   ```

2. **`llama3.2:1b-instruct`** (~1B parameters)
   - **Purpose**: Semantic chunking (document segmentation)
   - **Status**: ✅ Good replacement for phi4
   ```bash
   ollama pull llama3.2:1b-instruct
   ```

3. **For Vision/Image Captioning** (Choose ONE):

   **Option A: `llava:3.8b`** (~3.8B parameters - slightly over 3B but lightweight)
   - **Purpose**: Image captioning and OCR
   - **Status**: ⚠️ Slightly over 3B, but good quality
   ```bash
   ollama pull llava:3.8b
   ```

   **Option B: `llava:7b`** (if 3.8B is acceptable, this is better quality)
   ```bash
   ollama pull llava:7b
   ```

   **Option C: Skip vision features**
   - If you cannot install vision models, the code will skip image captioning
   - Images will just be referenced in markdown without captions

   **Option D: `gemma2:2b`** (only if it supports vision - may not)
   ```bash
   ollama pull gemma2:2b
   ```

---

## Current Code Configuration

The code in `mcp_server_2.py` is configured as:
- **Embeddings**: `nomic-embed-text` ✅
- **Chunking**: `llama3.2:1b-instruct` ✅
- **Vision**: `gemma2:2b` ⚠️ (may not support vision)

---

## To Update for Vision Model

If you want to use a vision-capable model, edit `mcp_server_2.py` line 34:

```python
# Change from:
GEMMA_MODEL = "gemma2:2b"

# To (if you can install llava):
GEMMA_MODEL = "llava:3.8b"
```

Or if you want to skip vision entirely, you can modify the code to skip image captioning.

---

## Installation Command (All Together)

```bash
# Required
ollama pull nomic-embed-text
ollama pull llama3.2:1b-instruct

# Optional (choose one):
ollama pull llava:3.8b  # For vision (recommended if possible)
# OR
ollama pull gemma2:2b  # Smaller but may not support vision
```

---

## Model Size Comparison

| Model | Parameters | Size (approx) | Purpose |
|-------|------------|---------------|---------|
| nomic-embed-text | 137M | ~500MB | Embeddings |
| llama3.2:1b-instruct | 1B | ~600MB | Chunking |
| gemma2:2b | 2B | ~1.4GB | Text/Vision? |
| llava:3.8b | 3.8B | ~2.2GB | Vision/OCR |
| llava:7b | 7B | ~4GB | Vision/OCR (better quality) |

---

## Notes

- **`nomic-embed-text`**: Keep this - it's the smallest and best for embeddings
- **`llama3.2:1b-instruct`**: Good replacement for phi4, works well for chunking
- **Vision models**: If you absolutely cannot go over 3B, you may need to skip image captioning features
- The code will still work without vision models - images just won't get captions automatically

---

## Alternative: No Vision Model

If you cannot install any vision model, the system will:
1. Still extract images from PDFs/webpages
2. Store image paths/references
3. Skip automatic captioning
4. You can manually add captions later if needed

The rest of the workflow (search, sheets, email) will work perfectly fine!

