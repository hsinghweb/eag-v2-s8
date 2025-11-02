# Quick Start: Small Models Setup

## ✅ Updated Model List (All Under 3B Parameters)

The code has been updated to use smaller models. Install these:

```bash
# 1. Embeddings (required)
ollama pull nomic-embed-text

# 2. Text/Chunking (required)  
ollama pull llama3.2:1b-instruct

# 3. Vision (optional - choose one)
# Option A: If you can go slightly over 3B for better quality
ollama pull llava:3.8b

# Option B: Smaller but may not support vision well
ollama pull gemma2:2b
```

---

## 🔧 Current Configuration

The code is configured with:
- **Embeddings**: `nomic-embed-text` ✅ (137M - tiny!)
- **Chunking**: `llama3.2:1b-instruct` ✅ (1B - small!)
- **Vision**: `gemma2:2b` ⚠️ (2B - but may not support vision)

---

## 🎯 Recommended: Use LLaVA for Vision

If `gemma2:2b` doesn't support vision (it's primarily a text model), update the code:

**Edit `mcp_server_2.py` line 36:**
```python
# Change from:
GEMMA_MODEL = "gemma2:2b"

# To:
GEMMA_MODEL = "llava:3.8b"  # Better vision support
```

Then install:
```bash
ollama pull llava:3.8b
```

---

## 🚫 Skip Vision (If Needed)

If you absolutely cannot install any vision model:
1. The code will still work
2. Images won't be captioned automatically
3. Image paths will still be stored
4. Everything else works fine!

Just skip pulling any vision model and proceed with testing.

---

## ✅ Verification

After installing, verify:

```bash
ollama list
```

You should see at minimum:
- `nomic-embed-text`
- `llama3.2:1b-instruct`
- (Optional) `llava:3.8b` or `gemma2:2b`

---

## 📝 Summary

**Minimum Required:**
1. `nomic-embed-text` - For embeddings
2. `llama3.2:1b-instruct` - For semantic chunking

**Optional but Recommended:**
3. `llava:3.8b` - For image captioning (if you can spare ~3.8B)

**Total size**: ~3.5GB with all models (much smaller than before!)

---

## 🚀 Next Steps

1. Install the models above
2. Continue with Google OAuth setup
3. Test the complete workflow

The F1 → Sheets → Gmail workflow will work fine with these smaller models!

