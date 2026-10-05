"""Relational-core models for the PokéAPI mirror.

These are the high-value / heavily-referenced resources promoted out of the
JSONB tail (src/models/api_resource.py) into proper tables. Kept flat: scalar
fields + FK ids only; nested arrays stay in the JSONB tail.
"""

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, Text

from src.models.base import Base


class Region(Base):
    __tablename__ = "regions"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    main_generation_id = Column(Integer)  # bare: region<->generation is circular


class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    main_region_id = Column(Integer)  # bare: circular with regions
    main_region_name = Column(String(100))


class VersionGroup(Base):
    __tablename__ = "version_groups"
    __table_args__ = (Index("idx_version_groups_gen", "generation_id"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    order_num = Column(Integer)
    generation_id = Column(Integer, ForeignKey("generations.id"))


class Version(Base):
    __tablename__ = "versions"
    __table_args__ = (Index("idx_versions_vg", "version_group_id"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    version_group_id = Column(Integer, ForeignKey("version_groups.id"))


class Pokedex(Base):
    __tablename__ = "pokedexes"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    is_main_series = Column(Boolean, nullable=False)
    region_id = Column(Integer, ForeignKey("regions.id"))


class ItemCategory(Base):
    __tablename__ = "item_categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    pocket_id = Column(Integer)  # item-pocket lives in the JSONB tail


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (Index("idx_items_category", "category_id"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    cost = Column(Integer)
    fling_power = Column(Integer)
    fling_effect_id = Column(Integer)  # item-fling-effect lives in the JSONB tail
    category_id = Column(Integer, ForeignKey("item_categories.id"))
    sprite_default = Column(Text)


class Berry(Base):
    __tablename__ = "berries"
    __table_args__ = (Index("idx_berries_item", "item_id"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    growth_time = Column(Integer)
    max_harvest = Column(Integer)
    natural_gift_power = Column(Integer)
    size = Column(Integer)
    smoothness = Column(Integer)
    soil_dryness = Column(Integer)
    firmness = Column(String(50))
    natural_gift_type = Column(String(50))
    item_id = Column(Integer, ForeignKey("items.id"))


class Machine(Base):
    __tablename__ = "machines"
    __table_args__ = (
        Index("idx_machines_item", "item_id"),
        Index("idx_machines_vg", "version_group_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # the TM/HM item slug
    item_id = Column(Integer, ForeignKey("items.id"))
    move_id = Column(Integer)  # bare: decouples machines from the moves load order
    version_group_id = Column(Integer, ForeignKey("version_groups.id"))


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (Index("idx_locations_region", "region_id"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    region_id = Column(Integer, ForeignKey("regions.id"))


class LocationArea(Base):
    __tablename__ = "location_areas"
    __table_args__ = (Index("idx_location_areas_loc", "location_id"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    game_index = Column(Integer)
    location_id = Column(Integer, ForeignKey("locations.id"))


class PokemonSpecies(Base):
    __tablename__ = "pokemon_species"
    __table_args__ = (Index("idx_species_generation", "generation_id"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    order_num = Column(Integer)
    gender_rate = Column(Integer)
    capture_rate = Column(Integer)
    base_happiness = Column(Integer)
    hatch_counter = Column(Integer)
    is_baby = Column(Boolean)
    is_legendary = Column(Boolean)
    is_mythical = Column(Boolean)
    has_gender_differences = Column(Boolean)
    forms_switchable = Column(Boolean)
    generation_id = Column(Integer, ForeignKey("generations.id"))
    evolution_chain_id = Column(Integer)  # evolution-chain is a tree -> JSONB tail
    evolves_from_species_id = Column(Integer)  # bare self-ref
    growth_rate = Column(String(50))
    color = Column(String(50))
    shape = Column(String(50))
    habitat = Column(String(50))


class EggGroup(Base):
    __tablename__ = "egg_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)


class Nature(Base):
    __tablename__ = "natures"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    decreased_stat = Column(String(50))
    increased_stat = Column(String(50))
    hates_flavor = Column(String(50))
    likes_flavor = Column(String(50))


class ContestType(Base):
    __tablename__ = "contest_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    berry_flavor = Column(String(50))
