import os
import re
import io
import html
import base64
import asyncio
import logging
import aiofiles
from PIL import Image
from urllib.parse import quote_plus
from pyrogram import filters

from kunal.bot import StreamBot
from kunal.vars import Var
from kunal.utils.file_properties import get_name, get_hash, get_media_file_size, get_media_from_message, create_mock_message
from kunal.utils.helpers import get_thumbnail_base64, humanbytes, get_shortlink
from kunal.utils.database import Database

logger = logging.getLogger(__name__)

db = Database(Var.DATABASE_URL, Var.name)

@StreamBot.on_message(filters.command("createhtml") & (filters.channel | filters.group | filters.private), group=-1)
async def create_html_handler(bot, message):
    chat_id = message.chat.id
    temp_msgs = [message]
    
    user_id = message.from_user.id if message.from_user else (message.sender_chat.id if message.sender_chat else "Unknown")
    logger.info(f"🤖 User {user_id} initiated /createhtml in chat {chat_id}")

    # -----------------------------------------------------
    # NEW: HIGH-QUALITY THUMBNAIL EXTRACTOR (RAM-BASED)
    # -----------------------------------------------------
    async def fetch_quality_thumbnail(b, msg):
        try:
            # If it's a photo, download it into memory and resize to a crisp size
            if getattr(msg, "photo", None):
                photo_bytes = await b.download_media(msg.photo.file_id, in_memory=True)
                if photo_bytes:
                    img = Image.open(photo_bytes)
                    # Convert to RGB to prevent transparency bugs in JPEG
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    # Resize keeping aspect ratio intact (max 500px)
                    img.thumbnail((500, 500))
                    
                    buffered = io.BytesIO()
                    img.save(buffered, format="JPEG", quality=85)
                    b64_encoded = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    return f"data:image/jpeg;base64,{b64_encoded}"
            
            # For video/document, fallback to the original default extractor
            b64_default = await get_thumbnail_base64(b, msg)
            # Ensure proper prefix is attached if it's missing
            if b64_default and not b64_default.startswith("data:"):
                return f"data:image/jpeg;base64,{b64_default}"
            return b64_default
            
        except Exception as e:
            logger.warning(f"Failed to generate quality thumbnail: {e}")
            return None
    # -----------------------------------------------------

    # -----------------------------------------------------
    # EXISTING: KUNAL FOLDER EXTRACTION LOGIC
    # -----------------------------------------------------
    def extract_folder_name(text: str) -> str:
        if not text: return "General"
        
        # 1. New Rule: '𝙄𝙣𝙙𝙚𝙭' enclosed by ━━━━━━━━━━
        if any(indicator in text for indicator in ['𝙄𝙣𝙙𝙚𝙭', 'Index', 'INDEX']):
            lines = text.split('\n')
            extracting = False
            extracted_name = ""
            for line in lines:
                clean_line = line.strip()
                if '━━' in clean_line:
                    if not extracting:
                        extracting = True
                        continue
                    else:
                        break # Found the closing separator
                elif extracting:
                    if clean_line:
                        extracted_name = clean_line
            if extracted_name:
                return extracted_name[:60].strip()

        # 2. Existing Rule: Subject / Topic Fallback
        subject, topic = None, None
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if any(k in line for k in ['𝐒𝐮𝐛𝐣𝐞𝐜𝐭:', 'Subject:', 'SUBJECT:']):
                parts = line.split(':', 1)
                if len(parts) > 1: subject = parts[1].strip()
            elif any(k in line for k in ['𝐓𝐨𝐩𝐢𝐜:', 'Topic:', 'TOPIC:']):
                parts = line.split(':', 1)
                if len(parts) > 1: topic = parts[1].strip()
                
        if subject and topic: return f"{subject} ({topic})"
        elif subject: return subject
        elif topic: return topic
        
        # 3. Fallback to the first non-separator line
        for line in lines:
            clean_line = line.strip()
            if clean_line and not all(c in '━-=_*| ' for c in clean_line):
                return clean_line[:60].strip()
        return lines[0][:60].strip() if lines else "General"
    # -----------------------------------------------------

    # -----------------------------------------------------
    # NEW: REAL FOLDER EXTRACTION LOGIC
    # -----------------------------------------------------
    def extract_real_folder_name(text: str) -> str:
        if not text: return "General"
        for line in text.split('\n'):
            # Remove HTML tags to simplify matching
            clean_line = re.sub(r'<[^>]+>', '', line).strip()
            # Match "Topic:" or "Topic -" with optional markdown (* or _) anywhere around them
            match = re.search(r'(?i)^[\*_]*topic[\*_]*\s*[:\-]\s*[\*_]*(.+)$', clean_line)
            if match:
                folder = match.group(1).strip()
                # Remove any trailing markdown asterisks or underscores from the extracted folder name
                folder = re.sub(r'[\*_]+$', '', folder).strip()
                return folder
        return "General"
    # -----------------------------------------------------

    # ASK FOR LOGIC CHOICE
    ask_logic = await message.reply_text(
        "**Which extraction logic do you want to use?**\n\n"
        "1. **Kunal Logic** (Extracts folders using divider messages and thread topics)\n"
        "2. **Real Logic** (Extracts category from `Topic: ...` directly from each media's caption)\n\n"
        "Reply with `1` or `2`:"
    )
    temp_msgs.append(ask_logic)
    logic_response = await bot.listen(chat_id)
    temp_msgs.append(logic_response)
    
    logic_input = (logic_response.text or "").strip().lower()
    logic_choice = "real" if logic_input in ["2", "real"] else "kunal"

    # ASK FOR URLS
    ask_url = await bot.send_message(
        chat_id,
        "Send URL(s) to generate HTML index:\n"
        "Single: `https://t.me/username/123` or `/c/123/123`\n"
        "Range: `https://t.me/username/123 to 150`"
    )
    temp_msgs.append(ask_url)
    response = await bot.listen(chat_id)
    temp_msgs.append(response)
    
    text_input = (response.text or "").strip()
    
    if not text_input:
        for msg in temp_msgs:
            try: await msg.delete()
            except Exception: pass
        return await bot.send_message(chat_id, "❌ Invalid input. Please send text only.")
        
    range_pattern = r"https://t\.me/(?:c/(\d+)|([\w_]+))/(\d+)\s*to\s*(\d+)"
    single_pattern = r"https://t\.me/(?:c/(\d+)|([\w_]+))/(\d+)"

    targets = []
    if re.match(range_pattern, text_input):
        match = re.match(range_pattern, text_input)
        is_private = match.group(1) is not None
        target_chat = int(f"-100{match.group(1)}") if is_private else match.group(2)
        start_id, end_id = int(match.group(3)), int(match.group(4))
        for i in range(start_id, end_id + 1):
            targets.append((target_chat, i))
    elif re.match(single_pattern, text_input):
        match = re.match(single_pattern, text_input)
        is_private = match.group(1) is not None
        target_chat = int(f"-100{match.group(1)}") if is_private else match.group(2)
        post_id = int(match.group(3))
        targets.append((target_chat, post_id))
    else:
        for msg in temp_msgs:
            try: await msg.delete()
            except Exception: pass
        return await bot.send_message(chat_id, "❌ Invalid URL format.")

    ask_sleep = await bot.send_message(chat_id, "Enter delay time between file processing in seconds (e.g., `2`):")
    temp_msgs.append(ask_sleep)
    sleep_response = await bot.listen(chat_id)
    temp_msgs.append(sleep_response)
    
    sleep_input = (sleep_response.text or "").strip()
    sleep_time = max(1, int(sleep_input)) if sleep_input.isdigit() else 2

    for msg in temp_msgs:
        try: await msg.delete()
        except Exception: pass

    mode_name = "Real Logic" if logic_choice == "real" else "Kunal Logic"
    status_msg = await bot.send_message(chat_id, f"⏳ Extracting ({mode_name}) and Generating HTML Index for {len(targets)} files...\nThis might take time as it downloads thumbnails.")
    
    # 1. Get Chat Info and encode DP to Base64
    channel_name = "Media Archive"
    channel_desc = "Generated by Zenith Streamer"
    dp_url = "https://i.ibb.co/M8S0Zzj/live-streaming.png"
    
    try:
        chat_info = await bot.get_chat(target_chat)
        channel_name = html.escape(chat_info.title or channel_name)
        channel_desc = html.escape(chat_info.description or channel_desc)
        
        if chat_info.photo:
            try:
                photo_path = await bot.download_media(chat_info.photo.big_file_id)
                with open(photo_path, "rb") as img_file:
                    dp_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                os.remove(photo_path)
                dp_url = f"data:image/jpeg;base64,{dp_base64}"
            except Exception as e:
                logger.warning(f"Could not convert DP to base64: {e}")
    except Exception as e:
        logger.warning(f"Could not fetch chat info: {e}")

    # 2. Process Target Messages & Topic Folders
    categories = {"General": []}
    folder_thumbs = {} # Store dynamically fetched folder images
    current_category = "General"
    
    v_count = 0
    d_count = 0
    i_count = 0
    success_count = 0

    topic_cache = {}

    for target, post_id in targets:
        try:
            original_message = await bot.get_messages(chat_id=target, message_ids=post_id)
            if not original_message or original_message.empty:
                continue

            text_content = original_message.caption or original_message.text or ""

            if logic_choice == "real":
                # ==========================================
                # REAL LOGIC: Read Topic directly from caption
                # ==========================================
                media = get_media_from_message(original_message)
                if not media:
                    continue  # Skip plain text messages completely in 'Real' mode
                
                folder_name = extract_real_folder_name(text_content)
                current_category = html.escape(folder_name)
                
                if current_category not in categories:
                    categories[current_category] = []
                
            else:
                # ==========================================
                # KUNAL LOGIC: Read from Dividers / Threads
                # ==========================================
                # --- Check for Thread/Topic ID in Groups ---
                thread_id = getattr(original_message, "message_thread_id", None)
                
                if thread_id:
                    if thread_id not in topic_cache:
                        try:
                            topic_starter = await bot.get_messages(target, thread_id)
                            if topic_starter and getattr(topic_starter, "forum_topic_created", None):
                                topic_cache[thread_id] = topic_starter.forum_topic_created.title
                            elif topic_starter and getattr(topic_starter, "text", None):
                                topic_cache[thread_id] = topic_starter.text.split("\n")[0][:40].strip()
                            else:
                                topic_cache[thread_id] = f"Topic {thread_id}"
                        except Exception as e:
                            logger.warning(f"Could not fetch topic info for thread {thread_id}: {e}")
                            topic_cache[thread_id] = f"Topic {thread_id}"
                    
                    current_category = html.escape(topic_cache[thread_id])
                    if current_category not in categories:
                        categories[current_category] = []
                # ------------------------------------------------

                # Topic / Folder Detection for Channels (Text or Image Dividers)
                is_folder_divider = False
                folder_name = "General"

                if not thread_id:
                    if original_message.text and not original_message.media:
                        is_folder_divider = True
                        folder_name = extract_folder_name(text_content)
                    elif original_message.photo:
                        if text_content and any(k in text_content for k in ['𝙄𝙣𝙙𝙚𝙭', 'Index', 'INDEX', '𝐒𝐮𝐛𝐣𝐞𝐜𝐭:', 'Subject:', 'SUBJECT:', '𝐓𝐨𝐩𝐢𝐜:', 'Topic:', 'TOPIC:']):
                            is_folder_divider = True
                            folder_name = extract_folder_name(text_content)
                        elif not text_content:
                            # Image with no caption acts as a 'General' folder divider
                            is_folder_divider = True
                            folder_name = "General"

                if is_folder_divider:
                    current_category = html.escape(folder_name)
                    if current_category not in categories:
                        categories[current_category] = []
                    
                    # Fetch and store the folder's image if the divider is a photo
                    if original_message.photo:
                        b64_thumb = await fetch_quality_thumbnail(bot, original_message)
                        if b64_thumb:
                            folder_thumbs[current_category] = b64_thumb
                    continue # Skip adding the divider itself as a clickable media item

                media = get_media_from_message(original_message)
                if not media:
                    continue

            # --- PROCESS AND ADD MEDIA CARD (Both Logics) ---
            forward_data = await db.get_forwarded(target, post_id)
            log_msg = None
            if forward_data:
                target_msg_id = forward_data.get('target_msg_id')
                media_type = forward_data.get('media_type')
                file_name = forward_data.get('file_name')
                file_hash = forward_data.get('file_hash')
                file_size = forward_data.get('file_size', 0)
                mime_type = forward_data.get('mime_type')
                
                if media_type and file_name and file_hash:
                    logger.info(f"⚡ [CACHE HIT] Found message {target}/{post_id} in Database. Skipping Telegram fetch.")
                    log_msg = create_mock_message(target_msg_id, media_type, file_name, file_hash, file_size, mime_type)
                else:
                    try:
                        logger.info(f"⏳ [CACHE HIT - OLD RECORD] Found target_msg_id={target_msg_id} for {target}/{post_id}. Fetching from Telegram to update cache...")
                        log_msg = await bot.get_messages(chat_id=Var.BIN_CHANNEL, message_ids=target_msg_id)
                        if getattr(log_msg, "empty", False):
                            log_msg = None
                        else:
                            # Update old cache with metadata
                            media = get_media_from_message(log_msg)
                            media_type = None
                            for attr in ("audio", "document", "photo", "sticker", "animation", "video", "voice", "video_note"):
                                if getattr(log_msg, attr, None):
                                    media_type = attr
                                    break
                            
                            file_name = getattr(media, "file_name", "")
                            file_hash = getattr(media, "file_unique_id", "")[:6]
                            file_size = getattr(media, "file_size", 0)
                            mime_type = getattr(media, "mime_type", "")
                            
                            await db.save_forwarded(
                                source_chat_id=target,
                                source_msg_id=post_id,
                                target_msg_id=log_msg.id,
                                media_type=media_type,
                                file_name=file_name,
                                file_hash=file_hash,
                                file_size=file_size,
                                mime_type=mime_type
                            )
                    except Exception:
                        log_msg = None

            if not log_msg:
                logger.info(f"📤 [FORWARD] Message {target}/{post_id} not cached. Forwarding to BIN_CHANNEL...")
                try:
                    log_msg = await original_message.copy(chat_id=Var.BIN_CHANNEL, reply_markup=None)
                except Exception as copy_err:
                    logger.warning(f"Direct copy failed for post {post_id}, attempting fallback: {copy_err}")
                    if getattr(original_message, "video", None):
                        log_msg = await bot.send_video(chat_id=Var.BIN_CHANNEL, video=media.file_id, caption=original_message.caption or "")
                    elif getattr(original_message, "photo", None):
                        log_msg = await bot.send_photo(chat_id=Var.BIN_CHANNEL, photo=media.file_id, caption=original_message.caption or "")
                    else:
                        log_msg = await bot.send_document(chat_id=Var.BIN_CHANNEL, document=media.file_id, caption=original_message.caption or "")
                
                if log_msg and not getattr(log_msg, "empty", False):
                    media = get_media_from_message(log_msg)
                    media_type = None
                    for attr in ("audio", "document", "photo", "sticker", "animation", "video", "voice", "video_note"):
                        if getattr(log_msg, attr, None):
                            media_type = attr
                            break
                    
                    file_name = getattr(media, "file_name", "")
                    file_hash = getattr(media, "file_unique_id", "")[:6]
                    file_size = getattr(media, "file_size", 0)
                    mime_type = getattr(media, "mime_type", "")
                    
                    await db.save_forwarded(
                        source_chat_id=target,
                        source_msg_id=post_id,
                        target_msg_id=log_msg.id,
                        media_type=media_type,
                        file_name=file_name,
                        file_hash=file_hash,
                        file_size=file_size,
                        mime_type=mime_type
                    )

            if not log_msg or getattr(log_msg, "empty", False):
                logger.error(f"❌ [HTML INDEX FAILED] Could not forward/retrieve message {target}/{post_id}")
                continue

            raw_name = get_name(log_msg) or ""
            name_quoted = quote_plus(raw_name)
            hash_val = get_hash(log_msg)
            
            # --- Categorize Item Type and assign Smart Icons ---
            ext = raw_name.split('.')[-1].lower() if '.' in raw_name else ""
            
            if getattr(original_message, "video", None):
                item_type = "video"
                icon = "🎬"
                v_count += 1
            elif getattr(original_message, "photo", None):
                item_type = "photo"
                icon = "🖼️"
                i_count += 1
            else:
                item_type = "document"
                d_count += 1
                if ext == "pdf": icon = "📕"
                elif ext in ["html", "htm"]: icon = "🌐"
                elif ext in ["zip", "rar", "7z", "tar"]: icon = "📦"
                elif ext == "apk": icon = "🤖"
                elif ext in ["txt", "md"]: icon = "📝"
                elif getattr(original_message, "audio", None) or ext in ["mp3", "m4a", "wav"]: icon = "🎵"
                else: icon = "📄"
            # ---------------------------------------------------
            
            stream_link = f"{Var.URL}watch/{log_msg.id}/{name_quoted}?hash={hash_val}"
            download_link = f"{Var.URL}{log_msg.id}/{name_quoted}?hash={hash_val}"
            
            if getattr(Var, 'SHORTLINK', None):
                stream_link = get_shortlink(stream_link) or stream_link
                download_link = get_shortlink(download_link) or download_link

            # Generate High-Quality Thumbnail safely
            b64_thumb = await fetch_quality_thumbnail(bot, original_message)
            thumb_style = f"background-image: url('{b64_thumb}'); background-size: cover; background-position: center;" if b64_thumb else ""
            thumb_content = "" if b64_thumb else icon
            
            size_str = humanbytes(get_media_file_size(original_message))
            clean_name = html.escape(raw_name)

            card_html = f'''
            <div class="card item-card" data-type="{item_type}" data-title="{clean_name.lower()}" data-folder="{current_category}">
                <div class="thumb" style="{thumb_style}">{thumb_content}</div>
                <div class="details">
                    <h3 class="title" title="{clean_name}">{clean_name}</h3>
                    <div class="meta">
                        <span>Size: {size_str}</span>
                        <span style="text-transform: capitalize;">{item_type}</span>
                    </div>
                    <div class="buttons">
                        <a href="{stream_link}" target="_blank" class="btn btn-stream">▶ Stream</a>
                        <a href="{download_link}" target="_blank" class="btn btn-dl">⬇ Download</a>
                    </div>
                </div>
            </div>
            '''
            
            categories[current_category].append(card_html)
            success_count += 1
            
            await asyncio.sleep(sleep_time)
            
            if success_count % 5 == 0:
                await status_msg.edit(f"⏳ Generating HTML Index ({mode_name})... Processed {success_count} files.")
                
        except Exception as e:
            logger.error(f"❌ Failed to process post {post_id} for HTML Index: {e}")

    # Remove empty categories
    categories = {k: v for k, v in categories.items() if len(v) > 0}
    
    # Generate Folder Grid Landing Page with Dynamic Folder Images
    folders_grid_html = '<div class="grid" id="folders-grid">\n'
    for folder, cards in categories.items():
        thumb_bg = folder_thumbs.get(folder)
        
        if thumb_bg:
            thumb_style = f"background-image: url('{thumb_bg}'); background-size: cover; background-position: center; height: 170px; border-radius: 18px; box-shadow: inset 0 0 30px rgba(0,0,0,0.6);"
            thumb_content = ""
        else:
            thumb_style = "background: transparent; box-shadow: none; font-size: 80px; height: 120px;"
            thumb_content = "📁"

        folders_grid_html += f'''
        <div class="card folder-card" onclick="openFolder('{folder}')">
            <div class="thumb" style="{thumb_style}">{thumb_content}</div>
            <div class="details" style="align-items: center; text-align: center; flex-grow: 0; margin-top: 10px;">
                <h3 class="title" style="margin-bottom: 8px; font-size: 20px;">{folder}</h3>
                <div class="meta" style="border: none; padding: 0; margin: 0; justify-content: center;">
                    <span style="background: var(--btn-dl-bg); padding: 5px 15px; border-radius: 12px; font-weight: 700;">{len(cards)} Items</span>
                </div>
            </div>
        </div>
        '''
    folders_grid_html += '</div>\n'

    # Generate Item Grids (All Hidden by Default)
    grids_html = ""
    for i, (folder, cards) in enumerate(categories.items()):
        grids_html += f'<div class="grid media-grid" id="folder-{folder}" style="display: none;">\n'
        grids_html += "".join(cards)
        grids_html += '</div>\n'

    # 3. Compile the Complete HTML Document
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{channel_name} - Media Index</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0f1115;
            --text: #f5f7fa;
            --muted: #aab2c0;
            --card-bg: rgba(30, 35, 45, 0.45);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent: #4da3ff;
            --accent-hover: #3b82f6;
            --blob1: #4da3ff;
            --blob2: #7c3aed;
            --btn-dl-bg: rgba(255, 255, 255, 0.08);
        }}
        body.light-mode {{
            --bg: #eef2f6;
            --text: #0f172a;
            --muted: #64748b;
            --card-bg: rgba(255, 255, 255, 0.65);
            --card-border: rgba(255, 255, 255, 0.4);
            --accent: #2563eb;
            --accent-hover: #1d4ed8;
            --blob1: #93c5fd;
            --blob2: #c4b5fd;
            --btn-dl-bg: rgba(0, 0, 0, 0.05);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text);
            min-height: 100vh; padding: 30px 20px; overflow-x: hidden;
            transition: background 0.5s ease, color 0.5s ease;
        }}
        
        /* Animated Background Blobs */
        .blob {{ position: fixed; border-radius: 50%; filter: blur(100px); z-index: -1; opacity: 0.4; animation: float 15s infinite alternate ease-in-out; pointer-events: none; }}
        .blob-1 {{ top: -10%; left: -10%; width: 40vw; height: 40vw; background: var(--blob1); transition: background 0.5s ease; }}
        .blob-2 {{ bottom: -10%; right: -10%; width: 35vw; height: 35vw; background: var(--blob2); animation-delay: -5s; transition: background 0.5s ease; }}
        @keyframes float {{ 0% {{ transform: translate(0, 0) scale(1); }} 100% {{ transform: translate(50px, 50px) scale(1.1); }} }}

        /* Theme Toggle */
        .theme-toggle {{
            position: absolute; top: 20px; right: 20px;
            background: var(--card-bg); border: 1px solid var(--card-border);
            border-radius: 50%; width: 50px; height: 50px;
            font-size: 22px; cursor: pointer; backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); display: flex; align-items: center; justify-content: center;
            color: var(--text); z-index: 100; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.1);
        }}
        .theme-toggle:hover {{ transform: scale(1.15) rotate(15deg); }}

        /* Header */
        .header {{ text-align: center; margin-bottom: 30px; animation: fadeIn 1s ease; position: relative; z-index: 1; }}
        .header img {{
            width: 120px; height: 120px; border-radius: 50%; object-fit: cover;
            border: 3px solid var(--accent); box-shadow: 0 10px 25px rgba(77, 163, 255, 0.3);
            margin-bottom: 15px; transition: transform 0.4s ease;
        }}
        .header img:hover {{ transform: scale(1.05); }}
        .header h1 {{ font-size: 32px; font-weight: 800; margin-bottom: 8px; letter-spacing: -0.5px; }}
        .header p {{ color: var(--muted); font-size: 16px; max-width: 600px; margin: 0 auto 25px; }}
        
        /* Search & Filters */
        .search-container {{ max-width: 600px; margin: 0 auto 25px; position: relative; z-index: 1; }}
        .search-container input {{
            width: 100%; padding: 16px 25px; border-radius: 30px; border: 1px solid var(--card-border);
            background: var(--card-bg); color: var(--text); font-size: 16px; outline: none;
            transition: all 0.4s ease; backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.05);
        }}
        .search-container input:focus {{ border-color: var(--accent); box-shadow: 0 10px 30px rgba(77, 163, 255, 0.2); transform: translateY(-2px); }}
        
        .filters {{ display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; margin-bottom: 25px; z-index: 1; position: relative; }}
        .filter-btn {{
            padding: 10px 20px; border-radius: 25px; border: 1px solid var(--card-border);
            background: var(--card-bg); color: var(--text); font-size: 14px; font-weight: 600;
            cursor: pointer; transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
        }}
        .filter-btn:hover {{ transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.1); }}
        .filter-btn.active {{ background: var(--accent); border-color: var(--accent); color: #fff; box-shadow: 0 8px 20px rgba(77, 163, 255, 0.3); }}
        
        /* Back Button */
        .back-btn-container {{ text-align: center; margin-bottom: 30px; position: relative; z-index: 1; }}
        .back-btn {{
            display: none;
            padding: 12px 28px; background: var(--card-bg); border: 1px solid var(--accent);
            color: var(--text); border-radius: 20px; font-size: 16px; font-weight: 700;
            cursor: pointer; backdrop-filter: blur(10px); transition: all 0.3s ease;
        }}
        .back-btn:hover {{ background: var(--accent); color: #fff; transform: translateY(-3px); box-shadow: 0 10px 20px rgba(77,163,255,0.2); }}

        /* Grid & Cards */
        .grid {{
            display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 30px; max-width: 1400px; margin: 0 auto; position: relative; z-index: 1;
        }}
        .card {{
            background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 28px;
            padding: 22px; display: flex; flex-direction: column; gap: 16px;
            backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1); transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            animation: fadeIn 0.6s ease forwards;
        }}
        .card:hover {{ transform: translateY(-12px); box-shadow: 0 25px 45px rgba(0, 0, 0, 0.2); border-color: var(--accent); }}
        
        /* Folder Specific Styles */
        .folder-card {{ cursor: pointer; justify-content: center; }}
        .folder-card:hover {{ border-color: var(--blob2); box-shadow: 0 20px 40px rgba(124, 58, 237, 0.2); }}

        .thumb {{
            height: 170px; display: flex; align-items: center; justify-content: center;
            font-size: 65px; background: rgba(0, 0, 0, 0.3); border-radius: 18px;
            box-shadow: inset 0 0 20px rgba(0,0,0,0.3); transition: transform 0.4s ease;
        }}
        .card.item-card:hover .thumb {{ transform: scale(1.03); }}
        
        .details {{ display: flex; flex-direction: column; flex-grow: 1; }}
        .title {{ font-size: 17px; font-weight: 700; margin-bottom: 12px; line-height: 1.4; word-break: break-all; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
        .meta {{ display: flex; justify-content: space-between; color: var(--muted); font-size: 14px; font-weight: 500; margin-bottom: 22px; padding-bottom: 18px; border-bottom: 1px solid var(--card-border); }}
        
        /* Buttons */
        .buttons {{ display: flex; gap: 14px; margin-top: auto; }}
        .btn {{ flex: 1; padding: 14px; border-radius: 16px; text-decoration: none; text-align: center; font-size: 15px; font-weight: 700; transition: all 0.3s ease; }}
        .btn-stream {{ background: linear-gradient(135deg, var(--accent), #6ab7ff); color: #fff; box-shadow: 0 6px 20px rgba(77, 163, 255, 0.25); border: none; }}
        .btn-stream:hover {{ box-shadow: 0 10px 25px rgba(77, 163, 255, 0.4); transform: translateY(-3px); }}
        .btn-dl {{ background: var(--btn-dl-bg); color: var(--text); border: 1px solid var(--card-border); }}
        .btn-dl:hover {{ background: var(--card-border); transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.1); }}

        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(30px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        @media (max-width: 600px) {{ 
            .grid {{ grid-template-columns: 1fr; gap: 20px; }} 
            .card {{ padding: 18px; border-radius: 24px; }}
            .thumb {{ height: 150px; border-radius: 14px; }}
            .theme-toggle {{ top: 15px; right: 15px; width: 40px; height: 40px; font-size: 18px; }}
            .header h1 {{ font-size: 26px; }}
        }}
    </style>
</head>
<body>
    <div class="blob blob-1"></div>
    <div class="blob blob-2"></div>

    <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle Theme">🌓</button>

    <div class="header">
        <img src="{dp_url}" alt="Channel Logo">
        <h1>{channel_name}</h1>
        <p>{channel_desc}</p>
        
        <div class="search-container">
            <input type="text" id="search" placeholder="🔍 Search across files..." onkeyup="filterCards()">
        </div>
        
        <div class="filters">
            <button class="filter-btn active" onclick="setFilter('all', this)">All ({success_count})</button>
            <button class="filter-btn" onclick="setFilter('video', this)">🎬 Videos ({v_count})</button>
            <button class="filter-btn" onclick="setFilter('photo', this)">🖼️ Images ({i_count})</button>
            <button class="filter-btn" onclick="setFilter('document', this)">📄 Documents ({d_count})</button>
        </div>
    </div>

    <div class="back-btn-container">
        <button class="back-btn" id="backBtn" onclick="showFolders()">⬅ Back to Folders</button>
    </div>

    <div id="folders-container">
        {folders_grid_html}
    </div>

    <div id="grids-container" style="display: none;">
        {grids_html}
    </div>

    <script>
        // Theme Toggle
        function toggleTheme() {{
            document.body.classList.toggle('light-mode');
            localStorage.setItem('theme', document.body.classList.contains('light-mode') ? 'light' : 'dark');
        }}
        if (localStorage.getItem('theme') === 'light') document.body.classList.add('light-mode');

        let isFolderView = true;
        let currentFolder = '';
        let currentFilter = 'all';

        function showFolders() {{
            isFolderView = true;
            currentFolder = '';
            document.getElementById('folders-container').style.display = 'block';
            document.getElementById('grids-container').style.display = 'none';
            document.getElementById('backBtn').style.display = 'none';
            document.getElementById('search').value = ''; 
            
            currentFilter = 'all';
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelector('.filter-btn').classList.add('active'); // Set 'All' as active
        }}

        function openFolder(folderName) {{
            isFolderView = false;
            currentFolder = folderName;
            
            document.getElementById('folders-container').style.display = 'none';
            document.getElementById('grids-container').style.display = 'block';
            document.getElementById('backBtn').style.display = 'inline-block';
            
            document.querySelectorAll('.grid.media-grid').forEach(grid => grid.style.display = 'none');
            document.getElementById('folder-' + folderName).style.display = 'grid';
            
            filterCards(); 
        }}

        function setFilter(type, btnElement) {{
            currentFilter = type;
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            if(btnElement) btnElement.classList.add('active');
            
            // If filtering while looking at the folders, automatically trigger global search mode
            if (isFolderView && type !== 'all') {{
                document.getElementById('folders-container').style.display = 'none';
                document.getElementById('grids-container').style.display = 'block';
                document.getElementById('backBtn').style.display = 'inline-block';
                isFolderView = false;
            }}
            filterCards();
        }}

        function filterCards() {{
            const query = document.getElementById('search').value.toLowerCase();
            
            // If typing in search while looking at folders, automatically trigger global search mode
            if (isFolderView && query.length > 0) {{
                document.getElementById('folders-container').style.display = 'none';
                document.getElementById('grids-container').style.display = 'block';
                document.getElementById('backBtn').style.display = 'inline-block';
                isFolderView = false;
            }}

            const isGlobalSearch = !currentFolder || query.length > 0 || currentFilter !== 'all';

            // Decide which grids to display
            if (isGlobalSearch) {{
                document.querySelectorAll('.grid.media-grid').forEach(grid => grid.style.display = 'grid');
            }} else if (currentFolder) {{
                document.querySelectorAll('.grid.media-grid').forEach(grid => grid.style.display = 'none');
                document.getElementById('folder-' + currentFolder).style.display = 'grid';
            }}

            const targetGrids = isGlobalSearch 
                ? document.querySelectorAll('.grid.media-grid') 
                : [document.getElementById('folder-' + currentFolder)];
            
            targetGrids.forEach(grid => {{
                let visibleCount = 0;
                const cards = grid.querySelectorAll('.card.item-card');
                
                cards.forEach(card => {{
                    const title = card.getAttribute('data-title');
                    const type = card.getAttribute('data-type');
                    const matchSearch = title.includes(query);
                    const matchType = (currentFilter === 'all') || (currentFilter === type);
                    
                    if (matchSearch && matchType) {{
                        card.style.display = 'flex';
                        visibleCount++;
                    }} else {{
                        card.style.display = 'none';
                    }}
                }});
                
                // Hide the parent grid entirely if no items match inside it (prevents empty gaps)
                if (isGlobalSearch) {{
                    grid.style.display = visibleCount > 0 ? 'grid' : 'none';
                }}
            }});
        }}
    </script>
</body>
</html>"""

    # 4. Save and Send the generated document back to the user
    file_path = f"Archive_{target_chat}.html"
    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(html_template)
        
    await status_msg.delete()
    
    await bot.send_document(
        chat_id=chat_id,
        document=file_path,
        caption=(
            f"✅ **Successfully Generated HTML Archive! ({mode_name})**\n\n"
            f"📌 **Channel:** `{channel_name}`\n"
            f"📁 **Categories/Folders:** `{len(categories)}`\n"
            f"🎬 **Videos:** `{v_count}`\n"
            f"🖼️ **Images:** `{i_count}`\n"
            f"📄 **Documents:** `{d_count}`\n"
            f"📊 **Total Linked:** `{success_count}`"
        ),
        file_name=f"{channel_name.replace(' ', '_')}_Archive.html"
    )
    
    # Cleanup temporary server file
    if os.path.exists(file_path):
        os.remove(file_path)
