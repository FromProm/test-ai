import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Wikipedia API 직접 사용
try:
    import wikipedia
    WIKIPEDIA_AVAILABLE = True
except ImportError:
    logger.warning("wikipedia library not installed. Run: pip install wikipedia")
    WIKIPEDIA_AVAILABLE = False

class WikipediaMCP:
    """Wikipedia API 직접 호출 래퍼"""
    
    def __init__(self, language: str = "en"):
        """
        Args:
            language: Wikipedia 언어 코드 (기본값: 'en', 한국어: 'ko')
        """
        self.language = language
        if WIKIPEDIA_AVAILABLE:
            wikipedia.set_lang(language)
    
    async def search_wikipedia(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Wikipedia 검색"""
        try:
            if not WIKIPEDIA_AVAILABLE:
                logger.error("wikipedia library not available")
                return {'results': [], 'status': 'error', 'error': 'wikipedia library not installed'}
            
            logger.info(f"Searching Wikipedia for: {query}")
            
            # Wikipedia API 직접 호출
            search_results = wikipedia.search(query, results=limit)
            
            results = []
            for title in search_results:
                results.append({
                    'title': title,
                    'timestamp': None  # 검색 결과에는 timestamp가 없음
                })
            
            return {
                'results': results,
                'status': 'success',
                'query': query,
                'count': len(results),
                'language': self.language
            }
            
        except Exception as e:
            logger.error(f"Wikipedia search failed for query '{query}': {str(e)}")
            return {'results': [], 'status': 'error', 'error': str(e)}
    
    async def get_article(self, title: str) -> Optional[Dict[str, Any]]:
        """Wikipedia 문서 내용 가져오기"""
        try:
            if not WIKIPEDIA_AVAILABLE:
                logger.error("wikipedia library not available")
                return None
            
            logger.info(f"Getting Wikipedia article: {title}")
            
            # Wikipedia API 직접 호출
            page = wikipedia.page(title, auto_suggest=False)
            
            return {
                'title': page.title,
                'text': page.content,
                'summary': page.summary,
                'url': page.url,
                'categories': page.categories if hasattr(page, 'categories') else []
            }
            
        except wikipedia.exceptions.DisambiguationError as e:
            logger.warning(f"Disambiguation page for '{title}': {e.options[:5]}")
            # 첫 번째 옵션으로 재시도
            if e.options:
                return await self.get_article(e.options[0])
            return None
        except wikipedia.exceptions.PageError:
            logger.warning(f"Wikipedia page not found: {title}")
            return None
        except Exception as e:
            logger.error(f"Failed to get Wikipedia article '{title}': {str(e)}")
            return None
    
    async def get_summary(self, title: str) -> Optional[Dict[str, Any]]:
        """Wikipedia 문서 요약 가져오기"""
        try:
            if not WIKIPEDIA_AVAILABLE:
                logger.error("wikipedia library not available")
                return None
            
            logger.info(f"Getting Wikipedia summary: {title}")
            
            # Wikipedia API 직접 호출
            summary = wikipedia.summary(title, auto_suggest=False)
            
            return {
                'title': title,
                'summary': summary
            }
            
        except wikipedia.exceptions.DisambiguationError as e:
            logger.warning(f"Disambiguation page for '{title}': {e.options[:5]}")
            if e.options:
                return await self.get_summary(e.options[0])
            return None
        except wikipedia.exceptions.PageError:
            logger.warning(f"Wikipedia page not found: {title}")
            return None
        except Exception as e:
            logger.error(f"Failed to get Wikipedia summary '{title}': {str(e)}")
            return None