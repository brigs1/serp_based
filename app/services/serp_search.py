from serpapi import GoogleSearch
from difflib import SequenceMatcher
import os
from datetime import datetime
import json
import time
import hashlib
import re
from app.services.cache_service import CacheService
from collections import Counter

class ScholarSearcher:
    def __init__(self):
        self.api_key = os.getenv('SERPAPI_KEY')
        self.cache = CacheService()

    def search_papers(self, keywords, num_pages=1):
        """키워드로 논문 검색"""
        try:
            query = ' OR '.join(f'"{keyword.strip()}"' for keyword in keywords)
            print(f"Search query: {query}")
            print(f"Fetching {num_pages} pages")
            
            all_papers = []
            results_per_page = 10
            total_found = 0
            
            for page in range(num_pages):
                params = {
                    "engine": "google_scholar",
                    "q": query,
                    "start": page * results_per_page,
                    "api_key": self.api_key,
                    "num": results_per_page,
                    "hl": "en"
                }
                
                print(f"Fetching page {page + 1}")
                results = self._make_api_request(params)
                
                if not results:
                    print("No results from API")
                    break
                    
                if 'error' in results:
                    print(f"API Error: {results['error']}")
                    break
                
                # 총 검색 결과 수 저장
                if page == 0 and 'search_information' in results:
                    total_found = results['search_information'].get('total_results', 0)
                    print(f"Total results found: {total_found}")
                
                if 'organic_results' not in results:
                    print("No organic_results in response")
                    break

                papers = self._process_search_results(results)
                if papers:
                    all_papers.extend(papers)
                    print(f"Added {len(papers)} papers from page {page + 1}")
                
                # 다음 조건들 중 하나라도 만족하면 중단:
                # 1. 요청한 페이지 수만큼 가져왔거나
                # 2. API가 더 이상 결과를 반환하지 않을 때
                if (page + 1) >= num_pages or not papers:
                    break
                    
                time.sleep(1)  # API 요청 간 딜레이
            
            # 인용 수로 정렬
            all_papers.sort(key=lambda x: x.get('citations', 0), reverse=True)
            
            return {
                'success': True,
                'papers': all_papers,
                'count': len(all_papers),
                'total_found': total_found,
                'query': query
            }
            
        except Exception as e:
            print(f"Search error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'query': query if 'query' in locals() else None
            }

    def get_paper_citations(self, paper_id, title, authors):
        """논문의 인용 정보 가져오기"""
        # 캐시 확인
        cache_result = self.cache.get_citation(paper_id)
        if cache_result:
            return cache_result['citation_count']

        first_author = authors.split(',')[0] if authors else ''
        params = {
            "engine": "google_scholar",
            "q": f'"{title}" author:"{first_author}"',
            "api_key": self.api_key
        }
        
        results = self._make_api_request(params)
        if not results:
            return 0

        citations = self._extract_citation_count(results, title)
        self.cache.update_citation(paper_id, title, authors, citations)
        return citations

    
    def get_citation_network(self, citation_id, search_within=None):
        """
        논문의 인용 네트워크 정보 가져오기
        
        Args:
            citation_id: 원본 논문의 ID
            search_within: 인용 논문 내에서 검색할 키워드 (optional)
        """
        try:
            print(f"Getting citation network for ID: {citation_id}")
            start_time = time.time()
            
            if not citation_id:
                print("Citation ID is missing")
                return None
            
            citing_papers = []
            start = 0
            max_papers = 1000  # API 제한 고려
            
            while True:
                params = {
                    "engine": "google_scholar",
                    "cites": citation_id,
                    "api_key": self.api_key,
                    "num": 100,
                    "start": start
                }
                
                # 검색어가 있으면 추가
                if search_within:
                    params["q"] = search_within
                
                print(f"Making API request with params (start={start})...")
                results = self._make_api_request(params)
                
                if not results:
                    print("No results from API")
                    break
                    
                if 'organic_results' not in results:
                    print(f"No organic_results in API response. Available keys: {results.keys()}")
                    break
                
                current_papers = results.get('organic_results', [])
                if not current_papers:
                    break
                    
                print(f"Found {len(current_papers)} results in current page")
                
                # 현재 페이지의 논문들 처리
                for paper in current_papers:
                    try:
                        # 출판 정보 추출
                        pub_info = paper.get('publication_info', {})
                        summary = pub_info.get('summary', '')
                        
                        # 연도 추출
                        year = self._extract_year(summary)
                        
                        # 인용 수 추출
                        citations = paper.get('inline_links', {}).get('cited_by', {}).get('total', 0)
                        
                        # 저자 정보 처리
                        authors = summary.split(' - ')[0] if ' - ' in summary else 'Unknown Authors'
                        
                        # 논문 정보 저장
                        paper_info = {
                            'title': paper.get('title', 'Unknown Title'),
                            'year': year or datetime.now().year,
                            'citations': citations,
                            'authors': authors,
                            'abstract': paper.get('snippet', 'No abstract available'),
                            'url': paper.get('link'),
                            'publication': summary.split(' - ')[1] if ' - ' in summary and len(summary.split(' - ')) > 1 else 'Unknown Publication'
                        }
                        
                        # 추가 링크 정보 (있는 경우)
                        inline_links = paper.get('inline_links', {})
                        if inline_links:
                            paper_info.update({
                                'pdf_link': inline_links.get('pdf', {}).get('link'),
                                'citations_link': inline_links.get('cited_by', {}).get('link'),
                                'versions_link': inline_links.get('versions', {}).get('link')
                            })
                        
                        citing_papers.append(paper_info)
                        
                    except Exception as e:
                        print(f"Error processing paper: {e}")
                        continue
                
                # 다음 페이지 준비
                start += len(current_papers)
                
                # 종료 조건 체크
                total_results = results.get('search_information', {}).get('total_results', 0)
                if start >= min(total_results, max_papers):
                    break
                    
                # API 제한 방지를 위한 딜레이
                time.sleep(2)
            
            # 분석을 위한 메타데이터 준비
            years = [paper['year'] for paper in citing_papers]
            year_distribution = Counter(years)
            
            # 최종 결과 정리
            network_data = {
                'citing_papers': citing_papers,
                'cited_papers': [],  # 현재 API로는 참조 논문을 가져올 수 없음
                'total_citations': results.get('search_information', {}).get('total_results', 0),
                'collected_citations': len(citing_papers),
                'metadata': {
                    'search_within': search_within,
                    'year_distribution': dict(year_distribution),
                    'search_time': time.time() - start_time,
                    'earliest_year': min(years) if years else None,
                    'latest_year': max(years) if years else None,
                    'average_citations': sum(p['citations'] for p in citing_papers) / len(citing_papers) if citing_papers else 0
                }
            }
            
            print(f"Network collection completed in {time.time() - start_time:.2f}s")
            print(f"Total available citations: {network_data['total_citations']}")
            print(f"Total papers collected: {len(citing_papers)}")
            
            if search_within:
                print(f"Search within results: found {len(citing_papers)} papers containing '{search_within}'")
            
            return network_data
                    
        except Exception as e:
            print(f"Error in get_citation_network: {e}")
            import traceback
            print(traceback.format_exc())
            return None


    def _process_paper(self, paper):
        try:
            pub_info = paper.get('publication_info', {})
            summary = pub_info.get('summary', '')
            
            year = self._extract_year(summary) or datetime.now().year
            citations = paper.get('inline_links', {}).get('cited_by', {}).get('total', 0)
            
            return {
                'title': paper.get('title', 'Unknown Title'),
                'year': year,
                'citations': citations,
                'authors': summary.split(' - ')[0] if ' - ' in summary else 'Unknown Authors',
                'abstract': paper.get('snippet', 'No abstract available')
            }
        except Exception as e:
            print(f"Error processing paper: {e}")
            return None



    def _get_citing_papers(self, cited_by_link):
        """인용 논문들의 정보를 가져오기"""
        if not cited_by_link:
            return []
            
        try:
            params = {
                "engine": "google_scholar",
                "q": cited_by_link,
                "api_key": self.api_key,
                "num": 100
            }
            
            results = self._make_api_request(params)
            citing_papers = []

            if results and 'organic_results' in results:
                for paper in results['organic_results']:
                    pub_info = paper.get('publication_info', {})
                    summary = pub_info.get('summary', '')
                    
                    # 연도 추출
                    year = None
                    if summary:
                        year_match = re.search(r'\b(19|20)\d{2}\b', summary)
                        if year_match:
                            year = int(year_match.group())
                    
                    citing_papers.append({
                        'title': paper.get('title', ''),
                        'year': year or datetime.now().year,
                        'citations': paper.get('inline_links', {}).get('cited_by', {}).get('total', 0),
                        'authors': summary.split(' - ')[0] if ' - ' in summary else 'Unknown'
                    })

            return citing_papers

        except Exception as e:
            print(f"Error getting citing papers: {e}")
            return []


    def _make_api_request(self, params):
        """SERP API 요청 수행"""
        try:
            if not self.api_key:
                raise ValueError("SERPAPI_KEY not configured")
                
            search = GoogleSearch(params)
            result = search.get_dict()
            
            print(f"API Response keys: {result.keys()}")  # 디버깅용
            
            # 에러 응답 상세 출력
            if 'error' in result:
                print(f"API Error detail: {result['error']}")
                
            # 응답 구조 디버깅
            if 'organic_results' in result:
                print(f"Found {len(result['organic_results'])} results")
                if result['organic_results']:
                    first_result = result['organic_results'][0]
                    print(f"First result keys: {first_result.keys()}")
            else:
                print("Response structure:", json.dumps(result, indent=2))
                
            return result
            
        except Exception as e:
            print(f"API request error: {str(e)}")
            return None

    def _process_search_results(self, results):
        """검색 결과 처리"""
        papers = []
        seen_titles = set()
        
        for result in results.get('organic_results', []):
            try:
                title = result.get('title')
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                
                # 저자 정보 처리 개선
                publication_info = result.get('publication_info', {})
                raw_authors = publication_info.get('authors', [])
                
                if isinstance(raw_authors, list):
                    authors = []
                    for author in raw_authors:
                        if isinstance(author, dict):
                            authors.append(author.get('name', ''))
                        elif isinstance(author, str):
                            authors.append(author)
                    authors = ', '.join(filter(None, authors))
                else:
                    authors = str(raw_authors)
                
                # 연도 추출 (summary에서)
                summary = publication_info.get('summary', '')
                year = self._extract_year(summary)
                
                # 인용 수 추출
                citations = result.get('inline_links', {}).get('cited_by', {}).get('total', 0)
                
                # 인용 ID 추출 (citation network에서 사용)
                citation_id = result.get('inline_links', {}).get('cited_by', {}).get('cites_id')
                
                paper = {
                    'title': title,
                    'authors': authors,
                    'year': year,
                    'citations': citations,
                    'abstract': result.get('snippet', 'No abstract available'),
                    'citation_id': citation_id  # 인용 ID 저장
                }
                
                papers.append(paper)
                
            except Exception as e:
                print(f"Error processing result: {e}")
                continue
        
        return papers

    def _extract_resource_links(self, result):
        """모든 가능한 리소스 링크 추출"""
        links = {
            'pdf_url': None,
            'html_url': None,
            'doi_url': None,
            'publisher_url': None,
            'repository_url': None,
            'preprint_url': None,
            'alternate_versions': [],
            'citations': None,
            'related_papers': None
        }
        
        # resources가 있는 경우에만 처리
        resources = result.get('resources', [])
        if isinstance(resources, list):  # resources가 리스트인지 확인
            for resource in resources:
                if isinstance(resource, dict):  # resource가 딕셔너리인지 확인
                    link = resource.get('link', '')
                    title = resource.get('title', '').lower()
                    
                    if link.endswith('.pdf'):
                        links['pdf_url'] = link
                    elif 'doi.org' in link:
                        links['doi_url'] = link
                    elif 'html' in title:
                        links['html_url'] = link
                    elif 'preprint' in title or 'arxiv' in link:
                        links['preprint_url'] = link
                    elif any(repo in link for repo in ['repository', 'institutional']):
                        links['repository_url'] = link
                    else:
                        links['publisher_url'] = link

        # 인라인 링크 처리
        inline_links = result.get('inline_links', {})
        if isinstance(inline_links, dict):
            cited_by = inline_links.get('cited_by', {})
            if isinstance(cited_by, dict):
                links['citations'] = cited_by.get('link')
            
            versions = inline_links.get('versions', {})
            if isinstance(versions, dict):
                links['alternate_versions'] = versions.get('link')
                
            links['related_papers'] = inline_links.get('related_pages_link')

        return links

    def _get_citing_papers(self, cited_by_link):
        """인용한 논문들 정보 가져오기"""
        params = {
            "engine": "google_scholar",
            "q": cited_by_link,
            "api_key": self.api_key,
            "num": 100
        }
        
        results = self._make_api_request(params)
        citing_papers = []

        if results and 'organic_results' in results:
            for result in results['organic_results']:
                paper = {
                    'title': result.get('title'),
                    'year': self._extract_year(result.get('publication_info', {}).get('summary', '')),
                    'authors': result.get('publication_info', {}).get('authors', []),
                    'citations': result.get('inline_links', {}).get('cited_by', {}).get('total', 0)
                }
                citing_papers.append(paper)

        return citing_papers

    def _extract_year(self, text):
        """출판 연도 추출"""
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        return int(year_match.group()) if year_match else datetime.now().year

    def _generate_paper_id(self, result):
        """논문 고유 ID 생성"""
        title = result.get('title', '')
        authors = result.get('publication_info', {}).get('authors', [])
        year = self._extract_year(result.get('publication_info', {}).get('summary', ''))
        
        # DOI나 다른 식별자가 있으면 사용
        for resource in result.get('resources', []):
            if 'doi.org' in resource.get('link', ''):
                return resource['link'].replace('https://doi.org/', '')
        
        # 없으면 해시 생성
        identifier = f"{title}_{'-'.join(authors)}_{year}"
        return hashlib.md5(identifier.encode()).hexdigest()

    def _match_titles(self, title1, title2, threshold=0.8):
        """제목 유사도 비교"""
        if not title1 or not title2:
            return False
        return SequenceMatcher(None, title1.lower(), title2.lower()).ratio() > threshold

    def _extract_citation_count(self, results, target_title):
        """인용 수 추출"""
        for result in results.get('organic_results', []):
            if self._match_titles(target_title, result.get('title', '')):
                return result.get('inline_links', {}).get('cited_by', {}).get('total', 0)
        return 0