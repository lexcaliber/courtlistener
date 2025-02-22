from django.utils.timezone import now
from factory import Faker, LazyFunction
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice
from localflavor.us.us_states import STATE_CHOICES

from cl.people_db.models import FEMALE, SUFFIXES, Person
from cl.tests.providers import LegalProvider

Faker.add_provider(LegalProvider)


class PersonFactory(DjangoModelFactory):
    class Meta:
        model = Person

    date_completed = LazyFunction(now)
    cl_id = Faker("random_id")
    name_first = Faker("name_female")
    name_last = Faker("last_name")
    name_suffix = FuzzyChoice(SUFFIXES, getter=lambda c: c[0])
    dob_city = Faker("city")
    dob_state = FuzzyChoice(STATE_CHOICES, getter=lambda c: c[0])
    gender = FEMALE
    slug = Faker("slug")
