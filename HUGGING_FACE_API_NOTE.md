# Hugging Face API Integration Note

## Status: Image Generation Temporarily Disabled

### Issue
As of January 2026, Hugging Face has deprecated their free Inference API (`api-inference.huggingface.co`). The new endpoint (`router.huggingface.co`) requires either:
- **Hugging Face Pro subscription** ($9/month)
- **Dedicated Inference Endpoints** (paid, custom pricing)
- **Self-hosted model deployment**

### Current Behavior
- Song artwork generation is **temporarily disabled**
- Reports use **styled music icons (🎵)** as fallback
- All other functionality works normally
- Hugging Face API key is configured but not actively used

### Code Structure
**File:** `generate_report.py`

```python
def generate_song_artwork(...):
    """
    Generate song artwork using Hugging Face's Stable Diffusion API.
    
    NOTE: Hugging Face's free Inference API has been deprecated.
    Image generation now requires paid subscription.
    
    For now, we'll use styled fallback icons.
    """
    return None  # Use styled music icon fallback
```

### Alternative Solutions

#### Option 1: Spotify Web API (Recommended)
Fetch actual album art from Spotify:

```python
import spotipy

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

results = sp.search(q=f"track:{title} artist:{artist}", limit=1)
if results['tracks']['items']:
    album_art_url = results['tracks']['items'][0]['album']['images'][0]['url']
```

**Pros:**
- Free API
- Real album artwork
- High quality images

**Cons:**
- Requires Spotify API credentials
- Adds API dependency

#### Option 2: MusicBrainz + Cover Art Archive
Free, no authentication required:

```python
import musicbrainzngs

musicbrainzngs.set_useragent("spotify-trading-bot", "1.0")
result = musicbrainzngs.search_recordings(recording=title, artist=artist, limit=1)
if result['recording-list']:
    release_id = result['recording-list'][0]['release-list'][0]['id']
    cover_url = f"https://coverartarchive.org/release/{release_id}/front"
```

**Pros:**
- Completely free
- No API key needed
- Real cover art

**Cons:**
- Less reliable (not all songs have covers)
- Slower API
- Requires fuzzy matching

#### Option 3: Static Placeholders
Use pre-generated generic music artwork:

```python
# Use different colors/gradients based on genre or confidence
def get_fallback_artwork(confidence):
    if confidence >= 7:
        return "gradient-green.png"
    elif confidence >= 5:
        return "gradient-yellow.png"
    else:
        return "gradient-red.png"
```

**Pros:**
- Fast
- No API dependencies
- Visual variety

**Cons:**
- Generic (not song-specific)
- Still need to create/host images

#### Option 4: Upgrade to Hugging Face Pro
Pay for Hugging Face Pro subscription:

**Pros:**
- Generated artwork matches song vibe
- Unlimited inference
- Latest AI models

**Cons:**
- Costs $9/month
- Overkill for just image generation

### Recommendation

**Best Option:** Use **Spotify Web API** (Option 1)

**Reasoning:**
- You're already scraping Spotify data from Kworb
- Free API access
- Real album artwork (professional quality)
- No additional costs
- Simple implementation

**Implementation:**
1. Add `spotipy` to `requirements.txt`
2. Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in GitHub Secrets
3. Update `generate_song_artwork()` to fetch from Spotify
4. Cache images to avoid repeated API calls

### Current Workflow Configuration

The GitHub Actions workflow already includes `HUGGING_FACE_API_KEY`:

```yaml
env:
  HUGGING_FACE_API_KEY: ${{ secrets.HUGGING_FACE_API_KEY }}
```

**Key:** `REDACTED`

This is configured but not actively used since image generation is disabled.

### Migration Path

If you want to re-enable image generation later:

1. **Subscribe to Hugging Face Pro** → Update API endpoint in code
2. **Use Spotify API** → Implement Option 1 above
3. **Self-host Stable Diffusion** → Deploy model to your server
4. **Use another service** → Replicate.com, DeepAI, etc.

---

## Bottom Line

Image generation is **temporarily disabled** due to Hugging Face API deprecation. The bot works perfectly with styled music icons as fallback. When ready to add real images, **Spotify Web API** is the recommended free solution.
