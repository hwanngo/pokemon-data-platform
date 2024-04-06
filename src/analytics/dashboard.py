"""Streamlit dashboard for Pokémon data visualization."""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, Any

from src.analytics.stats_analyzer import StatsAnalyzer
from src.analytics.type_analyzer import TypeAnalyzer

# Set page configuration
st.set_page_config(
    page_title="Pokémon Data Analytics Dashboard",
    page_icon="🐉",
    layout="wide"
)

def main():
    """Main function to run the Streamlit dashboard."""
    # Dashboard title
    st.title("Pokémon Data Analytics Dashboard")
    st.markdown("*Analyzing Pokémon from all generations*")
    
    # Initialize analyzers
    stats_analyzer = StatsAnalyzer()
    type_analyzer = TypeAnalyzer()
    
    # Create tabs for different analyses
    tab1, tab2, tab3, tab4 = st.tabs([
        "Top Pokémon Stats", 
        "Type Distribution", 
        "Type Effectiveness", 
        "Pokémon Analyzer"
    ])
    
    # Tab 1: Top Pokémon Stats
    with tab1:
        st.header("Top Pokémon by Base Stats")
        
        # Get top Pokémon by total base stats
        top_pokemon = stats_analyzer.get_top_pokemon_by_total_base_stats(limit=10)
        
        # Display as bar chart
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(x='name', y='total_base_stats', data=top_pokemon, ax=ax)
        ax.set_xlabel('Pokémon')
        ax.set_ylabel('Total Base Stats')
        ax.set_title('Top 10 Pokémon by Total Base Stats')
        plt.xticks(rotation=45, ha='right')
        st.pyplot(fig)
        
        # Display as table
        st.subheader("Data Table")
        st.dataframe(top_pokemon)
        
        # Show Pokémon with best move type coverage
        st.subheader("Pokémon with Best Move Type Coverage")
        best_coverage = stats_analyzer.get_pokemon_with_best_type_coverage(limit=10)
        st.dataframe(best_coverage)
    
    # Tab 2: Type Distribution
    with tab2:
        st.header("Type Distribution Analysis")
        
        # Get type distribution
        type_dist = stats_analyzer.get_type_distribution()
        
        # Display as pie chart
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.pie(type_dist['pokemon_count'], labels=type_dist['type_name'], autopct='%1.1f%%')
        ax.set_title('Distribution of Pokémon Types')
        st.pyplot(fig)
        
        # Display as table
        st.subheader("Type Distribution Data")
        st.dataframe(type_dist)
        
        # Show dual-type combinations
        st.subheader("Dual-Type Combinations")
        dual_types = stats_analyzer.get_dual_type_combinations()
        st.dataframe(dual_types)
    
    # Tab 3: Type Effectiveness
    with tab3:
        st.header("Type Effectiveness Analysis")
        
        # Get effectiveness matrix
        matrix = type_analyzer.get_effectiveness_matrix()
        
        # Display as heatmap
        st.subheader("Type Effectiveness Matrix")
        fig, ax = plt.subplots(figsize=(14, 12))
        sns.heatmap(matrix, annot=True, cmap="RdYlGn", ax=ax)
        ax.set_title('Type Effectiveness (Attacking → Defending)')
        st.pyplot(fig)
        
        # Show best attacking types
        st.subheader("Best Attacking Types")
        best_attacking = type_analyzer.find_best_attacking_types()
        st.dataframe(best_attacking)
        
        # Show best defensive types
        st.subheader("Best Defensive Types")
        best_defensive = type_analyzer.find_best_defensive_types()
        st.dataframe(best_defensive)
    
    # Tab 4: Pokémon Analyzer
    with tab4:
        st.header("Individual Pokémon Analysis")
        
        # Get list of all Pokémon for the dropdown
        pokemon_query = "SELECT id, name FROM pokemon ORDER BY id"
        pokemon_list = pd.read_sql(pokemon_query, stats_analyzer.db.bind)
        
        # Create a generation filter
        # Get generation data from the database
        generation_query = """
        SELECT DISTINCT generation_id, generation_name 
        FROM (
            SELECT 
                CASE 
                    WHEN id <= 151 THEN 1
                    WHEN id <= 251 THEN 2
                    WHEN id <= 386 THEN 3
                    WHEN id <= 493 THEN 4
                    WHEN id <= 649 THEN 5
                    WHEN id <= 721 THEN 6
                    WHEN id <= 809 THEN 7
                    WHEN id <= 898 THEN 8
                    ELSE 9
                END as generation_id,
                CASE 
                    WHEN id <= 151 THEN 'Generation I'
                    WHEN id <= 251 THEN 'Generation II'
                    WHEN id <= 386 THEN 'Generation III'
                    WHEN id <= 493 THEN 'Generation IV'
                    WHEN id <= 649 THEN 'Generation V'
                    WHEN id <= 721 THEN 'Generation VI'
                    WHEN id <= 809 THEN 'Generation VII'
                    WHEN id <= 898 THEN 'Generation VIII'
                    ELSE 'Generation IX and newer'
                END as generation_name
            FROM pokemon
        ) as generations
        ORDER BY generation_id
        """
        generations = pd.read_sql(generation_query, stats_analyzer.db.bind)
        
        # Add "All Generations" option
        all_gen_option = "All Generations"
        selected_generation = st.selectbox(
            "Filter by Generation",
            options=[all_gen_option] + generations['generation_name'].tolist()
        )
        
        # Filter Pokémon list by selected generation
        if selected_generation != all_gen_option:
            # Get the generation ID based on the selected name
            gen_id = generations[generations['generation_name'] == selected_generation]['generation_id'].values[0]
            
            # Apply generation filter to Pokémon list
            if gen_id == 1:
                filtered_pokemon = pokemon_list[pokemon_list['id'] <= 151]
            elif gen_id == 2:
                filtered_pokemon = pokemon_list[(pokemon_list['id'] > 151) & (pokemon_list['id'] <= 251)]
            elif gen_id == 3:
                filtered_pokemon = pokemon_list[(pokemon_list['id'] > 251) & (pokemon_list['id'] <= 386)]
            elif gen_id == 4:
                filtered_pokemon = pokemon_list[(pokemon_list['id'] > 386) & (pokemon_list['id'] <= 493)]
            elif gen_id == 5:
                filtered_pokemon = pokemon_list[(pokemon_list['id'] > 493) & (pokemon_list['id'] <= 649)]
            elif gen_id == 6:
                filtered_pokemon = pokemon_list[(pokemon_list['id'] > 649) & (pokemon_list['id'] <= 721)]
            elif gen_id == 7:
                filtered_pokemon = pokemon_list[(pokemon_list['id'] > 721) & (pokemon_list['id'] <= 809)]
            elif gen_id == 8:
                filtered_pokemon = pokemon_list[(pokemon_list['id'] > 809) & (pokemon_list['id'] <= 898)]
            else:  # gen_id == 9
                filtered_pokemon = pokemon_list[pokemon_list['id'] > 898]
        else:
            filtered_pokemon = pokemon_list
        
        # Create dropdown with filtered Pokémon names
        selected_pokemon = st.selectbox(
            "Select a Pokémon to analyze",
            options=filtered_pokemon['id'].tolist(),
            format_func=lambda x: f"#{x} - {pokemon_list[pokemon_list['id'] == x]['name'].values[0]}"
        )
        
        if selected_pokemon:
            # Get weakness profile
            weakness_profile = type_analyzer.get_pokemon_weakness_profile(selected_pokemon)
            
            # Display weakness profile as bar chart
            st.subheader("Type Effectiveness Against This Pokémon")
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.barplot(x='attacking_type', y='effectiveness', data=weakness_profile, ax=ax)
            ax.set_xlabel('Attacking Type')
            ax.set_ylabel('Effectiveness')
            ax.axhline(y=1.0, color='gray', linestyle='--')
            plt.xticks(rotation=45, ha='right')
            st.pyplot(fig)
            
            # Display counters
            st.subheader("Recommended Counter Types")
            counters = type_analyzer.recommend_counter_types(selected_pokemon)
            st.dataframe(counters[['attacking_type', 'effectiveness', 'description']])

if __name__ == "__main__":
    main()