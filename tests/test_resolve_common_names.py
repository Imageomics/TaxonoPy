import pytest
import polars as pl
from taxonopy.resolve_common_names import (
    merge_taxon_id, merge_common_name, prioritize_vernacular,
    normalize_taxonomic_columns, join_single_rank, 
    apply_hierarchical_common_name_lookup, override_input_common_name
)


class TestMergeTaxonId:
    """Unit tests for merge_taxon_id function"""
    
    def test_merge_taxon_id_basic_functionality(self):
        """Test that merge_taxon_id correctly assigns specific taxonIDs"""
        anno_df = pl.DataFrame({
            "uuid": ["test1", "test2"],
            "species": ["Canis lupus", "Felis catus"],
            "genus": ["Canis", "Felis"],
            "family": ["Canidae", "Felidae"],
            "order": ["Carnivora", "Carnivora"],
            "class": ["Mammalia", "Mammalia"],
            "phylum": ["Chordata", "Chordata"],
            "kingdom": ["Animalia", "Animalia"]
        })
        
        taxon_df = pl.DataFrame({
            "taxonID": [100, 200, 300, 400],
            "canonicalName": ["Canis lupus", "Felis catus", "Canis", "Felis"],
            "kingdom": ["Animalia", "Animalia", "Animalia", "Animalia"],
            "phylum": ["Chordata", "Chordata", "Chordata", "Chordata"],
            "class": ["Mammalia", "Mammalia", "Mammalia", "Mammalia"],
            "order": ["Carnivora", "Carnivora", "Carnivora", "Carnivora"],
            "family": ["Canidae", "Felidae", "Canidae", "Felidae"],
            "genus": ["Canis", "Felis", "Canis", "Felis"]
        })
        
        result = merge_taxon_id(anno_df, taxon_df)
        
        # Basic contract checks
        assert len(result) == len(anno_df), "Row count should be preserved"
        assert "taxonID_species" in result.columns, "Should add taxonID_species column"
        assert "taxonID_genus" in result.columns, "Should add taxonID_genus column"
        
        # Specific behavior checks
        canis_row = result.filter(pl.col("species") == "Canis lupus")
        assert canis_row["taxonID_species"].to_list()[0] == 100, "Canis lupus should get taxonID 100"
        assert canis_row["taxonID_genus"].to_list()[0] == 300, "Canis genus should get taxonID 300"
        
        felis_row = result.filter(pl.col("species") == "Felis catus") 
        assert felis_row["taxonID_species"].to_list()[0] == 200, "Felis catus should get taxonID 200"
        assert felis_row["taxonID_genus"].to_list()[0] == 400, "Felis genus should get taxonID 400"
    
    @pytest.mark.parametrize("missing_field,expected_null_column", [
        (("species", None), "taxonID_species"),
        (("species", ""), "taxonID_species"),
        (("genus", None), "taxonID_genus"), 
        (("genus", ""), "taxonID_genus"),
    ])
    def test_merge_taxon_id_handles_missing_data(self, missing_field, expected_null_column):
        """Test that merge_taxon_id handles missing/empty data gracefully"""
        field_name, field_value = missing_field
        
        anno_data = {
            "uuid": ["test1"],
            "species": ["Canis lupus"],
            "genus": ["Canis"],
            "family": ["Canidae"],
            "order": ["Carnivora"],
            "class": ["Mammalia"],
            "phylum": ["Chordata"],
            "kingdom": ["Animalia"]
        }
        anno_data[field_name] = [field_value]  # Override with test value
        anno_df = pl.DataFrame(anno_data)
        
        taxon_df = pl.DataFrame({
            "taxonID": [100, 300],
            "canonicalName": ["Canis lupus", "Canis"],
            "kingdom": ["Animalia", "Animalia"],
            "phylum": ["Chordata", "Chordata"],
            "class": ["Mammalia", "Mammalia"],
            "order": ["Carnivora", "Carnivora"],
            "family": ["Canidae", "Canidae"],
            "genus": ["Canis", "Canis"]
        })
        
        result = merge_taxon_id(anno_df, taxon_df)
        
        # Missing/empty fields should result in null taxonIDs
        assert len(result) == 1
        assert result[expected_null_column].to_list()[0] is None, f"Missing {field_name} should result in null {expected_null_column}"


class TestMergeCommonName:
    """Unit tests for merge_common_name function"""
    
    def test_merge_common_name_species_priority(self):
        """Test that species-level common names take priority"""
        anno_df = pl.DataFrame({
            "uuid": ["test1"],
            "species": ["Canis lupus"],
            "genus": ["Canis"],
            "family": ["Canidae"],
            "order": ["Carnivora"],
            "class": ["Mammalia"],
            "phylum": ["Chordata"],
            "kingdom": ["Animalia"],
            "taxonID_species": [100],
            "taxonID_genus": [300]
        })
        
        common_name_df = pl.DataFrame({
            "taxonID": [100, 300],
            "vernacularName": ["Gray Wolf", "Dog Genus"]
        })
        
        taxon_df = pl.DataFrame({
            "taxonID": [100, 300, 500],
            "canonicalName": ["Canis lupus", "Canis", "Canidae"],
            "taxonRank": ["species", "genus", "family"],
            "kingdom": ["Animalia"] * 3,
            "phylum": ["Chordata"] * 3,
            "class": ["Mammalia"] * 3,
            "order": ["Carnivora"] * 3,
            "family": ["Canidae"] * 3,
            "genus": ["Canis", "Canis", None]
        })
        
        result = merge_common_name(anno_df, common_name_df, taxon_df)
        
        assert len(result) == 1
        assert result["common_name"].to_list()[0] == "Gray Wolf", "Should prefer species over genus name"
    
    def test_merge_common_name_cleans_up_intermediate_columns(self):
        """Test that all intermediate columns are removed after processing"""
        anno_df = pl.DataFrame({
            "uuid": ["test1"],
            "species": ["Canis lupus"],
            "genus": ["Canis"],
            "family": ["Canidae"],
            "order": ["Carnivora"],
            "class": ["Mammalia"],
            "phylum": ["Chordata"],
            "kingdom": ["Animalia"],
            "taxonID_species": [100],
            "taxonID_genus": [300]
        })
        
        common_name_df = pl.DataFrame({
            "taxonID": [100],
            "vernacularName": ["Gray Wolf"]
        })
        
        taxon_df = pl.DataFrame({
            "taxonID": [100, 300, 500],
            "canonicalName": ["Canis lupus", "Canis", "Canidae"],
            "taxonRank": ["species", "genus", "family"],
            "kingdom": ["Animalia"] * 3,
            "phylum": ["Chordata"] * 3,
            "class": ["Mammalia"] * 3,
            "order": ["Carnivora"] * 3,
            "family": ["Canidae"] * 3,
            "genus": ["Canis", "Canis", None]
        })
        
        result = merge_common_name(anno_df, common_name_df, taxon_df)
        
        # Check that intermediate columns are cleaned up
        for col in result.columns:
            assert not col.startswith("vernacular_"), f"Should not have intermediate column: {col}"
            assert not col.startswith("taxonID_"), f"Should not have intermediate column: {col}"
        
        # Lock in the exact final column set
        expected_columns = {
            "uuid", "species", "genus", "family", "order", "class", "phylum", "kingdom", "common_name"
        }
        assert set(result.columns) == expected_columns, f"Final columns should be exactly {expected_columns}"
    
    def test_merge_common_name_overrides_existing_common_name(self):
        """
        Test that pre-existing common_name in input is overridden by backbone data.
        This is the core requirement from PR #10 - input data should not be given deference.
        """
        # Store original input common_name to verify it gets overridden
        original_input_name = "BAD INPUT NAME"
        
        anno_df = pl.DataFrame({
            "uuid": ["test1"],
            "species": ["Canis lupus"],
            "genus": ["Canis"],
            "family": ["Canidae"],
            "order": ["Carnivora"],
            "class": ["Mammalia"],
            "phylum": ["Chordata"],
            "kingdom": ["Animalia"],
            "common_name": [original_input_name],  # This should be completely replaced
            "taxonID_species": [100],
            "taxonID_genus": [300]
        })
        
        backbone_name = "Backbone Gray Wolf"
        common_name_df = pl.DataFrame({
            "taxonID": [100],
            "vernacularName": [backbone_name]
        })
        
        taxon_df = pl.DataFrame({
            "taxonID": [100, 300],
            "canonicalName": ["Canis lupus", "Canis"],
            "taxonRank": ["species", "genus"],
            "kingdom": ["Animalia"] * 2,
            "phylum": ["Chordata"] * 2,
            "class": ["Mammalia"] * 2,
            "order": ["Carnivora"] * 2,
            "family": ["Canidae"] * 2,
            "genus": ["Canis"] * 2
        })
        
        result = merge_common_name(anno_df, common_name_df, taxon_df)
        
        # Core PR requirement: original input common_name must be completely replaced
        final_common_name = result["common_name"].to_list()[0]
        assert final_common_name == backbone_name, "Must use backbone data for common name"
        assert final_common_name != original_input_name, "Must NOT use input data common name"
        
        # Verify that the original input common_name has been dropped and replaced
        # (not just appended to or modified)
        assert final_common_name == "Backbone Gray Wolf", "Should be exactly the backbone value"
        assert "BAD INPUT NAME" not in str(result), "Original input name should be completely gone"
        
        # Should only have the final common_name column, no intermediate columns
        for col in result.columns:
            assert not col.startswith("vernacular_"), f"Should not have intermediate column: {col}"
        
        # Verify exact final column set (original input had common_name, should be overridden)
        expected_columns = {
            "uuid", "species", "genus", "family", "order", "class", "phylum", "kingdom", "common_name"
        }
        assert set(result.columns) == expected_columns, f"Final columns should be exactly {expected_columns}"
    
    def test_merge_common_name_duplicate_vernacular_deterministic(self):
        """Test that merge_common_name handles duplicate vernacular names deterministically"""
        anno_df = pl.DataFrame({
            "uuid": ["test1"],
            "species": ["Canis lupus"],
            "genus": ["Canis"],
            "family": ["Canidae"],
            "taxonID_species": [100],
            "taxonID_genus": [300]
        })
        
        # Multiple vernacular names for same taxonID - first one should be selected
        common_name_df = pl.DataFrame({
            "taxonID": [100, 100, 300],
            "vernacularName": ["Gray Wolf", "Loup Gris", "Dog Genus"]
        })
        
        taxon_df = pl.DataFrame({
            "taxonID": [100, 300],
            "canonicalName": ["Canis lupus", "Canis"],
            "taxonRank": ["species", "genus"],
            "kingdom": ["Animalia"] * 2,
            "phylum": ["Chordata"] * 2,
            "class": ["Mammalia"] * 2,
            "order": ["Carnivora"] * 2,
            "family": ["Canidae"] * 2,
            "genus": ["Canis"] * 2
        })
        
        result = merge_common_name(anno_df, common_name_df, taxon_df)
        
        # Should deterministically pick the first vernacular name (Gray Wolf)
        assert result["common_name"].to_list()[0] == "Gray Wolf"
    
    @pytest.mark.parametrize("available_rank,expected_name", [
        ("species", "Species Name"),
        ("genus", "Genus Name"), 
        ("family", "Family Name"),
        ("order", "Order Name"),
        ("class", "Class Name"),
        ("phylum", "Phylum Name"),
        ("kingdom", "Kingdom Name"),
    ])
    def test_merge_common_name_hierarchical_fallback_levels(self, available_rank, expected_name):
        """Test hierarchical fallback at all taxonomic levels from species to kingdom"""
        anno_df = pl.DataFrame({
            "uuid": ["test1"],
            "species": ["Test species"],
            "genus": ["Test genus"],
            "family": ["Test family"],
            "order": ["Test order"],
            "class": ["Test class"],
            "phylum": ["Test phylum"],
            "kingdom": ["Test kingdom"],
            "taxonID_species": [999],  # Won't match
            "taxonID_genus": [998]     # Won't match
        })
        
        # Create taxonID based on rank being tested
        rank_to_taxonid = {
            "species": 100,
            "genus": 200,
            "family": 300,
            "order": 400,
            "class": 500,
            "phylum": 600,
            "kingdom": 700
        }
        
        common_name_df = pl.DataFrame({
            "taxonID": [rank_to_taxonid[available_rank]],
            "vernacularName": [expected_name]
        })
        
        taxon_df = pl.DataFrame({
            "taxonID": [rank_to_taxonid[available_rank]],
            "canonicalName": [f"Test {available_rank}"],
            "taxonRank": [available_rank],
            "kingdom": ["Test kingdom"],
            "phylum": ["Test phylum"],
            "class": ["Test class"],
            "order": ["Test order"],
            "family": ["Test family"],
            "genus": ["Test genus"]
        })
        
        result = merge_common_name(anno_df, common_name_df, taxon_df)
        
        assert result["common_name"].to_list()[0] == expected_name, f"Should fallback to {available_rank} level name"


class TestNormalizeTaxonomicColumns:
    """Unit tests for normalize_taxonomic_columns function"""
    
    def test_empty_strings_to_null(self):
        """Test that empty strings are converted to null"""
        df = pl.DataFrame({
            "species": ["", "Canis lupus", ""],
            "genus": ["Canis", "", "Felis"],
            "other_col": ["keep", "me", "unchanged"]
        })
        
        result = normalize_taxonomic_columns(df)
        
        assert result["species"].to_list() == [None, "Canis lupus", None]
        assert result["genus"].to_list() == ["Canis", None, "Felis"] 
        assert result["other_col"].to_list() == ["keep", "me", "unchanged"]
    
    def test_casts_to_utf8(self):
        """Test that columns are cast to Utf8"""
        df = pl.DataFrame({
            "species": [123, 456],  # Numeric input
            "genus": ["text", "already"]
        })
        
        result = normalize_taxonomic_columns(df)
        
        assert result["species"].dtype == pl.Utf8
        assert result["genus"].dtype == pl.Utf8
        assert result["species"].to_list() == ["123", "456"]


class TestJoinSingleRank:
    """Unit tests for join_single_rank function"""
    
    @pytest.mark.parametrize("rank", ["species", "genus"])
    def test_adds_taxonID_column(self, rank):
        """Test that join_single_rank adds taxonID_{rank} column"""
        anno_df = pl.DataFrame({
            rank: ["Canis"],
            "kingdom": ["Animalia"],
            "genus": ["Canis"]
        })
        
        taxon_df = pl.DataFrame({
            "canonicalName": ["Canis"],
            "taxonID": [42],
            "kingdom": ["Animalia"],
            "phylum": ["Chordata"],
            "class": ["Mammalia"],
            "order": ["Carnivora"],
            "family": ["Canidae"],
            "genus": ["Canis"]
        })
        
        result = join_single_rank(anno_df, taxon_df, rank)
        
        expected_col = f"taxonID_{rank}"
        assert expected_col in result.columns
        assert result[expected_col].to_list() == [42]
    
    def test_returns_unchanged_if_rank_missing(self):
        """Test that missing rank columns are handled gracefully"""
        anno_df = pl.DataFrame({"genus": ["Canis"]})
        taxon_df = pl.DataFrame({"canonicalName": ["Species"], "taxonID": [1]})
        
        result = join_single_rank(anno_df, taxon_df, "species")
        
        # Should return unchanged since species column doesn't exist
        assert result.equals(anno_df)


class TestHierarchicalCommonNameLookup:
    """Unit tests for apply_hierarchical_common_name_lookup function"""
    
    @pytest.mark.parametrize("available_rank,expected_name", [
        ("species", "Species Name"),
        ("genus", "Genus Name"), 
        ("family", "Family Name"),
    ])
    def test_hierarchical_fallback_levels(self, available_rank, expected_name):
        """Test hierarchical fallback at different taxonomic levels"""
        anno_df = pl.DataFrame({
            "uuid": ["test1"],
            f"taxonID_{available_rank}": [100]
        })
        
        common_lookup = pl.DataFrame({
            "taxonID": [100],
            "common_name": [expected_name]
        })
        
        result = apply_hierarchical_common_name_lookup(anno_df, common_lookup)
        
        assert result["common_name"].to_list()[0] == expected_name
    
    def test_species_takes_priority_over_genus(self):
        """Test that species-level names take priority over genus"""
        anno_df = pl.DataFrame({
            "uuid": ["test1"],
            "taxonID_species": [100],
            "taxonID_genus": [200]
        })
        
        common_lookup = pl.DataFrame({
            "taxonID": [100, 200],
            "common_name": ["Gray Wolf", "Dog Genus"]
        })
        
        result = apply_hierarchical_common_name_lookup(anno_df, common_lookup)
        
        assert result["common_name"].to_list()[0] == "Gray Wolf"


class TestOverrideInputCommonName:
    """Unit tests for override_input_common_name function"""
    
    def test_overrides_existing_common_name(self):
        """Test that pre-existing common_name is completely replaced"""
        df_with_input = pl.DataFrame({
            "uuid": ["test1"],
            "common_name": ["BAD INPUT NAME"],
            "taxonID_species": [100]
        })
        
        common_lookup = pl.DataFrame({
            "taxonID": [100],
            "common_name": ["Backbone Name"]
        })
        
        result = override_input_common_name(df_with_input, common_lookup)
        
        assert result["common_name"].to_list()[0] == "Backbone Name"
        assert "BAD INPUT NAME" not in str(result)
    
    def test_handles_no_existing_common_name(self):
        """Test that function works when no common_name column exists"""
        df_no_input = pl.DataFrame({
            "uuid": ["test1"],
            "taxonID_species": [100]
        })
        
        common_lookup = pl.DataFrame({
            "taxonID": [100],
            "common_name": ["Backbone Name"]
        })
        
        result = override_input_common_name(df_no_input, common_lookup)
        
        assert result["common_name"].to_list()[0] == "Backbone Name"


class TestEnglishPreference:
    """Test English language preference in vernacular name processing"""
    
    def test_english_preferred_over_other_languages(self):
        """Test the vernacular name processing logic that prefers English"""
        vernacular_df = pl.DataFrame({
            "taxonID": [100, 100, 200, 300],
            "vernacularName": ["Gray Wolf", "Loup gris", "House Cat", "Roble blanco"],
            "language": ["en", "fr", "en", "es"]
        })
        
        result = prioritize_vernacular(vernacular_df)
        
        # Check English preference
        wolf_name = result.filter(pl.col("taxonID") == 100)["vernacularName"].to_list()[0]
        assert wolf_name == "Gray Wolf", "Should prefer English 'Gray Wolf' over French 'Loup Gris'"
        
        cat_name = result.filter(pl.col("taxonID") == 200)["vernacularName"].to_list()[0] 
        assert cat_name == "House Cat", "Should use English name when only English available"
        
        # When only non-English available, should use that
        spanish_name = result.filter(pl.col("taxonID") == 300)["vernacularName"].to_list()[0]
        assert spanish_name == "Roble Blanco", "Should use non-English when English unavailable"


class TestDataIntegrity:
    """Tests to ensure data integrity through the pipeline"""
    
    def test_pipeline_preserves_row_count_and_uuids(self):
        """Test that the full pipeline preserves data integrity"""
        anno_df = pl.DataFrame({
            "uuid": ["uuid1", "uuid2", "uuid3"],
            "species": ["Canis lupus", "Felis catus", "Unknown species"],
            "genus": ["Canis", "Felis", "Unknown genus"],
            "family": ["Canidae", "Felidae", "Unknown family"],
            "order": ["Carnivora", "Carnivora", "Unknown order"],
            "class": ["Mammalia", "Mammalia", "Unknown class"],
            "phylum": ["Chordata", "Chordata", "Unknown phylum"],
            "kingdom": ["Animalia", "Animalia", "Unknown kingdom"]
        })
        
        taxon_df = pl.DataFrame({
            "taxonID": [100, 200, 300, 400],
            "canonicalName": ["Canis lupus", "Felis catus", "Canis", "Felis"],
            "taxonRank": ["species", "species", "genus", "genus"],
            "kingdom": ["Animalia"] * 4,
            "phylum": ["Chordata"] * 4,
            "class": ["Mammalia"] * 4,
            "order": ["Carnivora"] * 4,
            "family": ["Canidae", "Felidae", "Canidae", "Felidae"],
            "genus": ["Canis", "Felis", "Canis", "Felis"]
        })
        
        common_name_df = pl.DataFrame({
            "taxonID": [100, 200],
            "vernacularName": ["Gray Wolf", "House Cat"]
        })
        
        # Run full pipeline
        step1 = merge_taxon_id(anno_df, taxon_df)
        step2 = merge_common_name(step1, common_name_df, taxon_df)
        
        # Data integrity checks
        assert len(step2) == len(anno_df), "Row count should be preserved through pipeline"
        
        original_uuids = set(anno_df["uuid"].to_list())
        final_uuids = set(step2["uuid"].to_list())
        assert original_uuids == final_uuids, "All UUIDs should be preserved"
        assert len(step2["uuid"].unique()) == len(step2), "UUIDs should remain unique"
        
        # Should have final common names for matched taxa
        matched_rows = step2.filter(pl.col("common_name").is_not_null())
        assert len(matched_rows) >= 2, "Should have common names for at least the matched taxa"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])