import pytest
from syrupy.extensions.single_file import SingleFileAmberSnapshotExtension


@pytest.fixture
def snapshot(snapshot):
    return snapshot.use_extension(SingleFileAmberSnapshotExtension)
