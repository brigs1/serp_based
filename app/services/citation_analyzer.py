from collections import Counter
from datetime import datetime
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import NMF
import numpy as np

class CitationAnalyzer:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        
    def analyze_citations(self, citing_papers):
        """인용 논문들의 초록을 분석하여 연구 트렌드 파악"""
        if not citing_papers:
            return None
            
        # 연도별 정렬
        papers_by_year = {}
        for paper in citing_papers:
            year = str(paper.get('year', ''))
            if year not in papers_by_year:
                papers_by_year[year] = []
            papers_by_year[year].append(paper)
            
        # 초록 텍스트 준비
        abstracts = [p['abstract'] for p in citing_papers if p.get('abstract')]
        
        # 주제 모델링
        topics = self._extract_topics(abstracts)
        
        # 연도별 트렌드 분석
        year_trends = self._analyze_year_trends(papers_by_year)
        
        # 인용 영향력 분석
        influence = self._analyze_citation_influence(citing_papers)
        
        return {
            'topic_analysis': topics,
            'year_trends': year_trends,
            'citation_influence': influence,
            'total_papers': len(citing_papers)
        }
        
    def _extract_topics(self, abstracts, num_topics=3):
        """주제 모델링을 통한 주요 연구 주제 추출"""
        try:
            # TF-IDF 행렬 생성
            tfidf_matrix = self.vectorizer.fit_transform(abstracts)
            
            # NMF로 토픽 모델링
            nmf = NMF(n_components=num_topics, random_state=42)
            nmf_features = nmf.fit_transform(tfidf_matrix)
            
            # 각 토픽의 주요 키워드 추출
            feature_names = self.vectorizer.get_feature_names_out()
            topics = []
            
            for topic_idx, topic in enumerate(nmf.components_):
                top_words = [feature_names[i] for i in topic.argsort()[:-10:-1]]
                topics.append({
                    'id': topic_idx + 1,
                    'keywords': top_words,
                    'strength': float(np.mean(nmf_features[:, topic_idx]))
                })
            
            return topics
            
        except Exception as e:
            print(f"Topic modeling error: {e}")
            return []
    
    def _analyze_year_trends(self, papers_by_year):
        """연도별 연구 트렌드 분석"""
        trends = []
        years = sorted(papers_by_year.keys())
        
        for year in years:
            year_papers = papers_by_year[year]
            combined_abstract = " ".join([p['abstract'] for p in year_papers if p.get('abstract')])
            
            # 해당 연도의 주요 키워드 추출
            if combined_abstract:
                vectorizer = TfidfVectorizer(max_features=5, stop_words='english')
                try:
                    tfidf = vectorizer.fit_transform([combined_abstract])
                    keywords = vectorizer.get_feature_names_out()
                except:
                    keywords = []
            else:
                keywords = []
                
            trends.append({
                'year': year,
                'paper_count': len(year_papers),
                'keywords': keywords,
                'avg_citations': np.mean([p.get('citations', 0) for p in year_papers])
            })
        
        return trends
    
    def _analyze_citation_influence(self, citing_papers):
        """인용 영향력 분석"""
        total_citations = sum(p.get('citations', 0) for p in citing_papers)
        avg_citations = total_citations / len(citing_papers) if citing_papers else 0
        
        return {
            'total_citations': total_citations,
            'average_citations': avg_citations,
            'highly_cited': [p for p in citing_papers if p.get('citations', 0) > avg_citations]
        }