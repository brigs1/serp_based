from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from app.services.serp_search import ScholarSearcher
import plotly
import json
from datetime import datetime
from app.services.citation_analyzer import CitationAnalyzer

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return render_template('index.html')


@main.route('/search', methods=['POST'])
def search():
    try:
        keywords = request.form.getlist('keywords')
        num_pages = int(request.form.get('num_pages', 1))  # 기본값 1
        current_page = int(request.form.get('page', 1))  # 현재 페이지, 기본값 1
        
        # 페이지 수 제한
        num_pages = max(1, min(20, num_pages))
        
        print(f"Fetching {num_pages} pages of results")
        
        if not keywords:
            return render_template('results.html', 
                                success=False, 
                                error='No keywords provided')
        
        searcher = ScholarSearcher()
        if not searcher.api_key:
            raise ValueError("SERPAPI_KEY is not configured")
            
        # 검색 결과 가져오기
        search_results = searcher.search_papers(keywords, num_pages=num_pages)
        
        if 'error' in search_results:
            return render_template('results.html',
                                success=False,
                                error=search_results.get('error'),
                                original_keywords=keywords)
        
        # 추가 정보를 search_results 딕셔너리에 통합
        search_results.update({
            'current_page': current_page,
            'pages_fetched': num_pages
        })
        
        # 딕셔너리 언패킹으로 한 번만 전달
        return render_template('results.html', **search_results)
        
    except Exception as e:
        import traceback
        print(f"Error during search: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return render_template('results.html', 
                             success=False, 
                             error=str(e),
                             original_keywords=keywords)


def create_combined_timeline(papers):
    nodes = []
    edges = []
    
    # 모든 논문의 연도 범위 계산
    all_years = []
    for paper in papers:
        paper_year = int(paper.get('year', datetime.now().year))
        all_years.append(paper_year)
        for citing_paper in paper['citation_network']['citing_papers']:
            if citing_paper.get('year'):
                all_years.append(int(citing_paper['year']))
    
    min_year = min(all_years) if all_years else datetime.now().year - 10
    max_year = max(all_years) if all_years else datetime.now().year
    
    # 각 논문별 시각화
    for i, paper in enumerate(papers):
        paper_year = int(paper.get('year', min_year))
        
        # 원본 논문 노드
        nodes.append({
            'x': [paper_year],
            'y': [i * 6],  # 각 논문을 수직으로 분리
            'text': [f"{paper['title']}<br>Authors: {paper['authors']}<br>Total Citations: {paper['citation_network']['total_citations']}"],
            'mode': 'markers',
            'name': f"Paper {i+1}",
            'marker': {
                'size': [40],
                'color': f'rgb({50 + i*30}, {100 + i*20}, 255)',
                'symbol': 'circle'
            },
            'hovertemplate': '%{text}<br>Year: %{x}<extra></extra>'
        })
        
        # 인용 논문 노드들
        x = []
        y = []
        sizes = []
        texts = []
        
        for j, citing_paper in enumerate(paper['citation_network']['citing_papers']):
            year = int(citing_paper.get('year', max_year))
            citations = citing_paper.get('citations', 0)
            x.append(year)
            y.append(i * 6 + (j % 3 - 1))  # 같은 해의 논문들을 약간 분산
            sizes.append(15 + citations)
            texts.append(f"{citing_paper['title']}<br>Citations: {citations}")
            
            # 엣지 추가
            edges.append({
                'x': [paper_year, year],
                'y': [i * 6, i * 6 + (j % 3 - 1)],
                'mode': 'lines',
                'line': {'color': f'rgba({50 + i*30}, {100 + i*20}, 255, 0.3)', 'width': 1},
                'showlegend': False,
                'hoverinfo': 'none'
            })
    
    # 그래프 레이아웃
    layout = {
        'title': 'Combined Citation Network Over Time',
        'showlegend': True,
        'hovermode': 'closest',
        'xaxis': {
            'title': 'Year',
            'range': [min_year-1, max_year+1],
            'tickmode': 'linear'
        },
        'yaxis': {
            'showticklabels': False,
            'zeroline': False,
            'range': [-2, len(papers) * 6 + 2]
        },
        'height': max(800, len(papers) * 200),  # 논문 수에 따라 높이 조정
        'margin': {'l': 50, 'r': 50, 't': 100, 'b': 50}
    }
    
    return {'data': nodes + edges, 'layout': layout}


from urllib.parse import unquote

@main.route('/citation_network/<citation_id>')
def citation_network(citation_id):
    try:
        searcher = ScholarSearcher()
        analyzer = CitationAnalyzer()
        
        # 논문 정보 가져오기
        paper_info = {
            'title': unquote(request.args.get('title', '')),
            'authors': unquote(request.args.get('authors', '')),
            'year': request.args.get('year'),
            'citations': request.args.get('citations', '0'),
            'abstract': unquote(request.args.get('abstract', '')),
            'citation_id': citation_id
        }
        
        # 네트워크 데이터 가져오기
        network_data = searcher.get_citation_network(citation_id)
        if not network_data:
            flash('Unable to retrieve citation network data.', 'error')
            return render_template('citation_network.html',
                                paper_info=paper_info,
                                network_data={'citing_papers': [], 'total_citations': 0},
                                analysis={})
            
        # 인용 분석 수행
        analysis_results = analyzer.analyze_citations(network_data['citing_papers'])
        
        return render_template('citation_network.html',
                             paper_info=paper_info,
                             network_data=network_data,
                             analysis=analysis_results)
                             
    except Exception as e:
        print(f"Error in citation_network: {e}")
        flash(f'An error occurred: {str(e)}', 'error')
        return render_template('citation_network.html',
                             paper_info=paper_info if 'paper_info' in locals() else {},
                             network_data={'citing_papers': [], 'total_citations': 0},
                             analysis={},
                             error=str(e))
    

@main.route('/api/citation_network/<citation_id>')
def get_citation_network_data(citation_id):
    """인용 네트워크 데이터를 JSON으로 반환하는 API 엔드포인트"""
    try:
        searcher = ScholarSearcher()
        
        # 원본 논문 정보 가져오기
        paper_info = searcher.get_paper_info(citation_id)
        if not paper_info:
            return jsonify({'error': 'Paper not found'})
            
        # 인용 네트워크 데이터 가져오기
        network_data = searcher.get_citation_network(paper_info['title'], citation_id)
        if not network_data:
            network_data = {'citing_papers': [], 'cited_papers': []}
            
        return jsonify({
            'paper_info': paper_info,
            'network_data': network_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})