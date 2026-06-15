import time
import logging
import queue
import threading
import re
import shutil
import csv
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from src.downloader import evaluate_image_quality

_log = logging.getLogger(__name__)

def log_quality_evaluation(
    deck_dir: Path,
    card_name: str,
    card_set: str,
    card_cn: str,
    file_path: Path,
    method: str,
    score: float,
    status: str
) -> None:
    """
    Appends a row to the downloaded_images_quality.csv log file inside the deck directory.
    Converts file_path to be relative to the workspace root.
    """
    csv_path = deck_dir / "downloaded_images_quality.csv"
    try:
        app_root = Path(__file__).resolve().parent.parent
        try:
            rel_path = file_path.relative_to(app_root)
        except ValueError:
            rel_path = file_path

        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([card_name, card_set, card_cn, str(rel_path), method, f"{score:.2f}", status])
    except Exception as e:
        _log.error(f"Failed to log quality evaluation to CSV for {card_name}: {e}")


# Track last request time to enforce 0.5s rate limiting
_last_request_time = 0.0
_request_lock = threading.Lock()

def sanitize_filename(name: str) -> str:
    """Removes filesystem-unsafe and special punctuation characters from card name."""
    clean = re.sub(r'[\\/*?:"<>|!\',]', "", name)
    clean = clean.replace(" ", "_")
    return clean

def scryfall_get(session: requests.Session, url: str, params: dict = None) -> requests.Response:
    global _last_request_time
    with _request_lock:
        elapsed = time.time() - _last_request_time
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)
        _last_request_time = time.time()
        
    _log.info(f"Scryfall HTTP GET: {url} with params {params}")
    resp = session.get(url, params=params, timeout=15)
    return resp

def create_scryfall_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "MPCFillToPDF/1.0 (contact: github.com/fmolinagomez/MPCFillToPDF)",
        "Accept": "application/json"
    })
    retries = Retry(total=3, backoff_factor=1.0, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def search_exact_print(session: requests.Session, card_name: str, card_set: str, card_cn: str, lang: str) -> dict | None:
    url = "https://api.scryfall.com/cards/search"
    # Search set, cn and lang
    q = f'set:{card_set} cn:{card_cn} lang:{lang}'
    try:
        resp = scryfall_get(session, url, params={"q": q})
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                return data["data"][0]
        elif resp.status_code != 404:
            _log.warning(f"Search exact print for {card_name} ({card_set}/{card_cn}) in {lang} returned status: {resp.status_code}")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise e
    except Exception as e:
        _log.error(f"Error searching exact print for {card_name} ({card_set}/{card_cn}) in {lang}: {e}")
    return None

def search_all_prints(session: requests.Session, oracle_id: str, lang: str) -> list[dict]:
    url = "https://api.scryfall.com/cards/search"
    q = f'oracle_id:{oracle_id} lang:{lang}'
    prints = []
    page_url = url
    params = {"q": q, "unique": "prints"}
    try:
        while page_url:
            resp = scryfall_get(session, page_url, params=params)
            params = None  # only use params on first request
            if resp.status_code != 200:
                if resp.status_code != 404:
                    _log.warning(f"Search all prints for oracle_id {oracle_id} in {lang} returned status: {resp.status_code}")
                break
            data = resp.json()
            prints.extend(data.get("data", []))
            page_url = data.get("next_page")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise e
    except Exception as e:
        _log.error(f"Error searching prints for oracle_id {oracle_id} in {lang}: {e}")
    return prints

def get_oracle_id(session: requests.Session, card_name: str, card_set: str, card_cn: str) -> str | None:
    # Look up exact English print to get oracle_id
    card = search_exact_print(session, card_name, card_set, card_cn, "en")
    if card:
        return card.get("oracle_id")
    # Fallback to name search
    url = "https://api.scryfall.com/cards/named"
    try:
        resp = scryfall_get(session, url, params={"exact": card_name})
        if resp.status_code == 200:
            return resp.json().get("oracle_id")
        else:
            _log.warning(f"Get oracle ID by name for {card_name} returned status: {resp.status_code}")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise e
    except Exception as e:
        _log.error(f"Error getting oracle ID by name for {card_name}: {e}")
    return None

def download_image_file(session: requests.Session, url: str, dest_path: Path, cancel_event: threading.Event) -> tuple[bool, str]:
    if cancel_event.is_set():
        return False, "Cancelled"
    try:
        resp = scryfall_get(session, url)
        if resp.status_code == 200:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            return True, ""
        else:
            reason = f"HTTP Error {resp.status_code}"
            return False, reason
    except requests.exceptions.Timeout as e:
        return False, "Connection timeout"
    except requests.exceptions.ConnectionError as e:
        return False, "Connection error"
    except Exception as e:
        return False, f"Download error: {str(e)}"

def get_cached_card(
    card_name: str,
    card_set: str,
    card_cn: str,
    is_dfc: bool,
    threshold: int,
    deck_dir: Path,
    cache_dir: Path,
    quality_method: str = "pillow",
    log_eval: bool = True
) -> float | None:
    prefix = f"{sanitize_filename(card_name)}_{sanitize_filename(card_set)}_{sanitize_filename(card_cn)}"
    if not is_dfc:
        cache_path = cache_dir / f"{prefix}.png"
        if cache_path.exists():
            q = evaluate_image_quality(cache_path, method=quality_method)
            status = "Cached" if q >= threshold else "Rejected (Below Threshold)"
            if log_eval:
                log_quality_evaluation(deck_dir, card_name, card_set, card_cn, cache_path, quality_method, q, status)
            if q >= threshold:
                deck_path = deck_dir / f"{prefix}.png"
                deck_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(cache_path, deck_path)
                return q
    else:
        cache_front = cache_dir / f"{prefix}_front.png"
        cache_back = cache_dir / f"{prefix}_back.png"
        if cache_front.exists() and cache_back.exists():
            q_front = evaluate_image_quality(cache_front, method=quality_method)
            q_back = evaluate_image_quality(cache_back, method=quality_method)
            q = min(q_front, q_back)
            status = "Cached" if q >= threshold else "Rejected (Below Threshold)"
            if log_eval:
                log_quality_evaluation(deck_dir, card_name, card_set, card_cn, cache_front, quality_method, q_front, status)
                log_quality_evaluation(deck_dir, card_name, card_set, card_cn, cache_back, quality_method, q_back, status)
            if q >= threshold:
                deck_front = deck_dir / f"{prefix}_front.png"
                deck_back = deck_dir / f"{prefix}_back.png"
                deck_front.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(cache_front, deck_front)
                shutil.copy(cache_back, deck_back)
                return q
    return None


def download_card_from_scryfall_object(
    session: requests.Session,
    card_obj: dict,
    card_name: str,
    card_set: str,
    card_cn: str,
    deck_dir: Path,
    cache_dir: Path,
    cancel_event: threading.Event,
    threshold: int = 100,
    quality_method: str = "pillow",
    log_eval: bool = True
) -> tuple[bool, float, bool, str]:
    prefix = f"{sanitize_filename(card_name)}_{sanitize_filename(card_set)}_{sanitize_filename(card_cn)}"
    
    # Check if DFC
    is_dfc = False
    card_faces = card_obj.get("card_faces")
    if card_faces and len(card_faces) >= 2 and "image_uris" in card_faces[0]:
        is_dfc = True

    if not is_dfc:
        image_uris = card_obj.get("image_uris")
        if not image_uris or "png" not in image_uris:
            return False, 0.0, False, "Missing image URIs in Scryfall data"
        url = image_uris["png"]
        
        temp_path = deck_dir / f"{prefix}_temp.png"
        success, err_reason = download_image_file(session, url, temp_path, cancel_event)
        if not success:
            if temp_path.exists():
                temp_path.unlink()
            return False, 0.0, False, err_reason
        
        q = evaluate_image_quality(temp_path, method=quality_method)
        status = "Accepted" if q >= threshold else "Rejected (Below Threshold)"
        final_path = deck_dir / f"{prefix}.png"
        if log_eval:
            log_quality_evaluation(deck_dir, card_name, card_set, card_cn, final_path, quality_method, q, status)
        if temp_path.exists():
            temp_path.replace(final_path)
            
        cache_path = cache_dir / f"{prefix}.png"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(final_path, cache_path)
        
        return True, q, False, ""
    else:
        front_face = card_faces[0]
        back_face = card_faces[1]
        front_uris = front_face.get("image_uris")
        back_uris = back_face.get("image_uris")
        if not front_uris or "png" not in front_uris or not back_uris or "png" not in back_uris:
            return False, 0.0, True, "Missing DFC image URIs in Scryfall data"
            
        url_front = front_uris["png"]
        url_back = back_uris["png"]
        
        temp_front = deck_dir / f"{prefix}_front_temp.png"
        temp_back = deck_dir / f"{prefix}_back_temp.png"
        
        success_front, err_front = download_image_file(session, url_front, temp_front, cancel_event)
        if not success_front:
            for p in [temp_front, temp_back]:
                if p.exists():
                    p.unlink()
            return False, 0.0, True, f"Front face: {err_front}"
            
        success_back, err_back = download_image_file(session, url_back, temp_back, cancel_event)
        if not success_back:
            for p in [temp_front, temp_back]:
                if p.exists():
                    p.unlink()
            return False, 0.0, True, f"Back face: {err_back}"
            
        q_front = evaluate_image_quality(temp_front, method=quality_method)
        q_back = evaluate_image_quality(temp_back, method=quality_method)
        q = min(q_front, q_back)
        status = "Accepted" if q >= threshold else "Rejected (Below Threshold)"
        final_front = deck_dir / f"{prefix}_front.png"
        final_back = deck_dir / f"{prefix}_back.png"
        if log_eval:
            log_quality_evaluation(deck_dir, card_name, card_set, card_cn, final_front, quality_method, q_front, status)
            log_quality_evaluation(deck_dir, card_name, card_set, card_cn, final_back, quality_method, q_back, status)
        
        if temp_front.exists():
            temp_front.replace(final_front)
        if temp_back.exists():
            temp_back.replace(final_back)
            
        cache_front = cache_dir / f"{prefix}_front.png"
        cache_back = cache_dir / f"{prefix}_back.png"
        cache_front.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy(final_front, cache_front)
        shutil.copy(final_back, cache_back)
        
        return True, q, True, ""


def process_exact_edition(
    session: requests.Session,
    card_name: str,
    card_set: str,
    card_cn: str,
    prefer_spanish: bool,
    threshold: int,
    deck_dir: Path,
    cache_dir: Path,
    cancel_event: threading.Event,
    quality_method: str = "pillow"
) -> tuple[bool, str]:
    try:
        oracle_id = None
        attempts = []
        
        # 1. If prefer_spanish, try exact Spanish
        if prefer_spanish:
            card_obj = search_exact_print(session, card_name, card_set, card_cn, "es")
            if card_obj:
                oracle_id = card_obj.get("oracle_id")
                is_dfc = (card_obj.get("card_faces") and len(card_obj["card_faces"]) >= 2 and "image_uris" in card_obj["card_faces"][0])
                
                cached_q = get_cached_card(card_name, card_set, card_cn, is_dfc, threshold, deck_dir, cache_dir, quality_method=quality_method)
                if cached_q is not None:
                    _log.info(f"Cache hit for exact Spanish card: {card_name}")
                    return True, ""
                    
                success, q, is_dfc, err = download_card_from_scryfall_object(
                    session, card_obj, card_name, card_set, card_cn, deck_dir, cache_dir, cancel_event, threshold, quality_method=quality_method
                )
                if success and q >= threshold:
                    return True, ""
                else:
                    prefix = f"{sanitize_filename(card_name)}_{sanitize_filename(card_set)}_{sanitize_filename(card_cn)}"
                    for suffix in ["", "_front", "_back"]:
                        p = deck_dir / f"{prefix}{suffix}.png"
                        if p.exists():
                            p.unlink()
                    if success:
                        attempts.append({"lang": "es", "set": card_set, "cn": card_cn, "quality": q, "error": "quality"})
                    else:
                        attempts.append({"lang": "es", "set": card_set, "cn": card_cn, "error": err})
            else:
                attempts.append({"lang": "es", "set": card_set, "cn": card_cn, "error": "Print not found"})
                            
            # 2. Try alternative Spanish prints
            if not oracle_id:
                oracle_id = get_oracle_id(session, card_name, card_set, card_cn)
                
            if oracle_id:
                alt_prints = search_all_prints(session, oracle_id, "es")
                for alt in alt_prints:
                    if cancel_event.is_set():
                        return False, "Cancelled"
                    if alt.get("set", "").upper() == card_set.upper() and alt.get("collector_number") == card_cn:
                        continue
                        
                    alt_set = alt.get("set", "").upper()
                    alt_cn = alt.get("collector_number", "")
                    alt_is_dfc = (alt.get("card_faces") and len(alt["card_faces"]) >= 2 and "image_uris" in alt["card_faces"][0])
                    
                    cached_q = get_cached_card(card_name, alt_set, alt_cn, alt_is_dfc, threshold, deck_dir, cache_dir, quality_method=quality_method)
                    if cached_q is not None:
                        _log.info(f"Cache hit for alternative Spanish card: {card_name} ({alt_set}/{alt_cn})")
                        return True, ""
                        
                    success, q, alt_is_dfc, err = download_card_from_scryfall_object(
                        session, alt, card_name, alt_set, alt_cn, deck_dir, cache_dir, cancel_event, threshold, quality_method=quality_method
                    )
                    if success and q >= threshold:
                        return True, ""
                    else:
                        prefix = f"{sanitize_filename(card_name)}_{sanitize_filename(alt_set)}_{sanitize_filename(alt_cn)}"
                        for suffix in ["", "_front", "_back"]:
                            p = deck_dir / f"{prefix}{suffix}.png"
                            if p.exists():
                                p.unlink()
                        if success:
                            attempts.append({"lang": "es", "set": alt_set, "cn": alt_cn, "quality": q, "error": "quality"})
                        else:
                            attempts.append({"lang": "es", "set": alt_set, "cn": alt_cn, "error": err})
            else:
                attempts.append({"lang": "es", "error": "Could not find oracle ID"})

        # 3. Try exact English
        card_obj = search_exact_print(session, card_name, card_set, card_cn, "en")
        if card_obj:
            oracle_id = card_obj.get("oracle_id")
            is_dfc = (card_obj.get("card_faces") and len(card_obj["card_faces"]) >= 2 and "image_uris" in card_obj["card_faces"][0])
            
            cached_q = get_cached_card(card_name, card_set, card_cn, is_dfc, threshold, deck_dir, cache_dir, quality_method=quality_method)
            if cached_q is not None:
                _log.info(f"Cache hit for exact English card: {card_name}")
                return True, ""
                
            success, q, is_dfc, err = download_card_from_scryfall_object(
                session, card_obj, card_name, card_set, card_cn, deck_dir, cache_dir, cancel_event, threshold, quality_method=quality_method
            )
            if success and q >= threshold:
                return True, ""
            else:
                prefix = f"{sanitize_filename(card_name)}_{sanitize_filename(card_set)}_{sanitize_filename(card_cn)}"
                for suffix in ["", "_front", "_back"]:
                    p = deck_dir / f"{prefix}{suffix}.png"
                    if p.exists():
                        p.unlink()
                if success:
                    attempts.append({"lang": "en", "set": card_set, "cn": card_cn, "quality": q, "error": "quality"})
                else:
                    attempts.append({"lang": "en", "set": card_set, "cn": card_cn, "error": err})
        else:
            attempts.append({"lang": "en", "set": card_set, "cn": card_cn, "error": "Print not found"})

        # 4. Try alternative English prints
        if not oracle_id:
            oracle_id = get_oracle_id(session, card_name, card_set, card_cn)
            
        if oracle_id:
            alt_prints = search_all_prints(session, oracle_id, "en")
            for alt in alt_prints:
                if cancel_event.is_set():
                    return False, "Cancelled"
                if alt.get("set", "").upper() == card_set.upper() and alt.get("collector_number") == card_cn:
                    continue
                    
                alt_set = alt.get("set", "").upper()
                alt_cn = alt.get("collector_number", "")
                alt_is_dfc = (alt.get("card_faces") and len(alt["card_faces"]) >= 2 and "image_uris" in alt["card_faces"][0])
                
                cached_q = get_cached_card(card_name, alt_set, alt_cn, alt_is_dfc, threshold, deck_dir, cache_dir, quality_method=quality_method)
                if cached_q is not None:
                    _log.info(f"Cache hit for alternative English card: {card_name} ({alt_set}/{alt_cn})")
                    return True, ""
                    
                success, q, alt_is_dfc, err = download_card_from_scryfall_object(
                    session, alt, card_name, alt_set, alt_cn, deck_dir, cache_dir, cancel_event, threshold, quality_method=quality_method
                )
                if success and q >= threshold:
                    return True, ""
                else:
                    prefix = f"{sanitize_filename(card_name)}_{sanitize_filename(alt_set)}_{sanitize_filename(alt_cn)}"
                    for suffix in ["", "_front", "_back"]:
                        p = deck_dir / f"{prefix}{suffix}.png"
                        if p.exists():
                            p.unlink()
                    if success:
                        attempts.append({"lang": "en", "set": alt_set, "cn": alt_cn, "quality": q, "error": "quality"})
                    else:
                        attempts.append({"lang": "en", "set": alt_set, "cn": alt_cn, "error": err})
        else:
            attempts.append({"lang": "en", "error": "Could not find oracle ID"})

        # Analyze attempts to return the most helpful error message
        for att in attempts:
            err = att.get("error", "")
            if isinstance(err, str) and ("connection" in err.lower() or "timeout" in err.lower()):
                return False, f"Connection issue: {err}"
                
        qualities = [att["quality"] for att in attempts if att.get("error") == "quality"]
        if qualities:
            best_quality = max(qualities)
            return False, f"Image quality issue: Best score was {best_quality:.1f} (threshold: {threshold})"
            
        non_not_found = [att.get("error") for att in attempts if att.get("error") not in ("Print not found", "Could not find oracle ID")]
        if non_not_found:
            return False, f"Download issue: {non_not_found[0]}"
            
        return False, "Scryfall database issue: Print not found"
    except requests.exceptions.Timeout as e:
        return False, "Connection issue: Connection timeout"
    except requests.exceptions.ConnectionError as e:
        return False, "Connection issue: Connection error"

def process_best_image(
    session: requests.Session,
    card_name: str,
    card_set: str,
    card_cn: str,
    prefer_spanish: bool,
    threshold: int,
    deck_dir: Path,
    cache_dir: Path,
    cancel_event: threading.Event,
    quality_method: str = "pillow"
) -> tuple[bool, str]:
    try:
        oracle_id = get_oracle_id(session, card_name, card_set, card_cn)
        if not oracle_id:
            return False, "Could not find oracle ID"
            
        languages_to_try = []
        if prefer_spanish:
            languages_to_try.append("es")
        languages_to_try.append("en")
        
        attempts = []
        
        for lang in languages_to_try:
            if cancel_event.is_set():
                return False, "Cancelled"
                
            prints = search_all_prints(session, oracle_id, lang)
            if not prints:
                attempts.append({"lang": lang, "error": f"No prints found in {lang}"})
                continue
                
            best_q = -1.0
            best_print = None
            best_is_dfc = False
            
            for pr in prints:
                if cancel_event.is_set():
                    return False, "Cancelled"
                    
                p_set = pr.get("set", "").upper()
                p_cn = pr.get("collector_number", "")
                p_is_dfc = (pr.get("card_faces") and len(pr["card_faces"]) >= 2 and "image_uris" in pr["card_faces"][0])
                
                cached_q = get_cached_card(card_name, p_set, p_cn, p_is_dfc, threshold, deck_dir, cache_dir, quality_method=quality_method)
                if cached_q is not None:
                    prefix = f"{sanitize_filename(card_name)}_{sanitize_filename(p_set)}_{sanitize_filename(p_cn)}"
                    for suffix in ["", "_front", "_back"]:
                        p = deck_dir / f"{prefix}{suffix}.png"
                        if p.exists():
                            p.unlink()
                    if cached_q > best_q:
                        best_q = cached_q
                        best_print = pr
                        best_is_dfc = p_is_dfc
                    continue
                    
                success, q, is_dfc, err = download_card_from_scryfall_object(
                    session, pr, card_name, p_set, p_cn, deck_dir, cache_dir, cancel_event, threshold, quality_method=quality_method
                )
                if success:
                    prefix = f"{sanitize_filename(card_name)}_{sanitize_filename(p_set)}_{sanitize_filename(p_cn)}"
                    for suffix in ["", "_front", "_back"]:
                        p = deck_dir / f"{prefix}{suffix}.png"
                        if p.exists():
                            p.unlink()
                    if q > best_q:
                        best_q = q
                        best_print = pr
                        best_is_dfc = is_dfc
                else:
                    attempts.append({"lang": lang, "set": p_set, "cn": p_cn, "error": err})
                    
            if best_print and best_q >= threshold:
                best_set = best_print.get("set", "").upper()
                best_cn = best_print.get("collector_number", "")
                get_cached_card(card_name, best_set, best_cn, best_is_dfc, threshold, deck_dir, cache_dir, quality_method=quality_method, log_eval=False)
                return True, ""
            elif best_print:
                attempts.append({"lang": lang, "best_q": best_q, "error": "quality"})
                
        for att in attempts:
            err = att.get("error", "")
            if isinstance(err, str) and ("connection" in err.lower() or "timeout" in err.lower()):
                return False, f"Connection issue: {err}"
                
        qualities = [att["best_q"] for att in attempts if att.get("error") == "quality"]
        if qualities:
            best_quality = max(qualities)
            return False, f"Image quality issue: Best score was {best_quality:.1f} (threshold: {threshold})"
            
        non_not_found = [att.get("error") for att in attempts if att.get("error") and "No prints found" not in att.get("error")]
        if non_not_found:
            return False, f"Download issue: {non_not_found[0]}"
            
        return False, "Scryfall database issue: Print not found"
    except requests.exceptions.Timeout as e:
        return False, "Connection issue: Connection timeout"
    except requests.exceptions.ConnectionError as e:
        return False, "Connection issue: Connection error"

def download_deck_images(
    deck_data: dict,
    event_queue: queue.Queue,
    cancel_event: threading.Event,
    exact_edition: bool = True,
    best_image: bool = False,
    prefer_spanish: bool = True,
    zones: dict = None,
    quality_threshold: int = 100,
    quality_method: str = "pillow"
) -> None:
    try:
        if zones is None:
            zones = {
                "commanders": True,
                "mainboard": True,
                "sideboard": False,
                "tokens": False
            }

        app_root = Path(__file__).resolve().parent.parent
        deck_name = deck_data.get("name", "Moxfield_Deck")
        deck_id = deck_data.get("id", "Unknown")
        
        deck_dir = app_root / "workdir" / "scryfall" / f"{sanitize_filename(deck_name)}_{sanitize_filename(deck_id)}"
        cache_dir = app_root / "workdir" / "scryfall_cache"
        
        deck_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize downloaded_images_quality.csv with headers
        csv_path = deck_dir / "downloaded_images_quality.csv"
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Card Name", "Set", "Collector Number", "File Path", "Method", "Quality Score", "Status"])
        except Exception as e:
            _log.error(f"Failed to initialize CSV log: {e}")


        all_cards = []
        for zone_name, is_selected in zones.items():
            if is_selected and zone_name in deck_data:
                for card in deck_data[zone_name]:
                    all_cards.append(card)

        unique_cards = []
        seen = set()
        for card in all_cards:
            key = (card.get("name", ""), card.get("set", ""), card.get("cn", ""))
            if key not in seen:
                seen.add(key)
                unique_cards.append(card)

        total_cards = len(unique_cards)
        _log.info(f"Starting Scryfall download for {total_cards} unique cards")
        event_queue.put(("scryfall_download_start", total_cards))

        if total_cards == 0:
            event_queue.put(("scryfall_download_success", 0, []))
            return

        session = create_scryfall_session()
        failed_cards = []

        for index, card in enumerate(unique_cards, start=1):
            if cancel_event.is_set():
                _log.info("Scryfall download cancelled by user")
                return

            card_name = card.get("name", "Unknown Card")
            card_set = card.get("set", "").upper()
            card_cn = card.get("cn", "")
            
            percent = int((index / total_cards) * 100)
            event_queue.put(("scryfall_download_progress", index, total_cards, percent, card_name))
            
            if best_image:
                success, reason = process_best_image(
                    session, card_name, card_set, card_cn, prefer_spanish, quality_threshold, deck_dir, cache_dir, cancel_event, quality_method=quality_method
                )
            else:
                success, reason = process_exact_edition(
                    session, card_name, card_set, card_cn, prefer_spanish, quality_threshold, deck_dir, cache_dir, cancel_event, quality_method=quality_method
                )
                
            if not success and not cancel_event.is_set():
                _log.warning(f"Failed to download/evaluate {card_name}: {reason}")
                failed_cards.append(f"{card_name} ({reason})")

        if failed_cards:
            report_path = deck_dir / "missing_cards.txt"
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write("Las siguientes cartas no se pudieron descargar o no cumplieron con el umbral de calidad:\n\n")
                    for entry in failed_cards:
                        f.write(f"- {entry}\n")
            except Exception as e:
                _log.error(f"Error writing missing_cards.txt: {e}")

        event_queue.put(("scryfall_download_success", total_cards, failed_cards))
        _log.info("Scryfall download process finished")

    except Exception as e:
        _log.exception("Error in Scryfall downloader thread")
        event_queue.put(("scryfall_download_error", str(e)))
