/*
This is used to automatically add an inheritable relation to self 
so children are "tagged" to that place without duplication of maintenance.
This enables events to be "rolled up" to parent places.

For example, a note with label 'land' will get an inheritable relation 
~land=(self).

It needs to handle 2 case:
- Notes manually created in UI: will be invoked with originEntity
as the newly created note, and it will already have inherited attributes
from its template
- Notes created in ETAPI automation: can't be created with template in
one shot, so check if originEntity is a template relation and use
that to determine if new relation should be created (inherited attributes
won't be populated yet)

This could be made more generic or possibly templated and configured
in Python.
*/

let place = null;
let template = null;

if (api.originEntity.hasOwnProperty('attributeId')) {
    /* have attribute; it may be a template in which case inherited
    attributes won't be populated yet, so lookup target of template */

    place = api.getNote(api.originEntity.noteId);

    if (api.originEntity.name === 'template') {
        /* lookup template target */
        template = api.getNote(api.originEntity.value);
    }
} else {
    /* have note, it should already have inherited attributes populated */
    place = api.originEntity;
    template = api.originEntity;
}

if ((place === null) || (template == null)) {
    return;
}

let hasLabel = template.hasLabel('land');

if (template.hasLabel('land') && !place.hasRelation('land')) {
    place.addRelation('land', place.noteId, true);
} else if (template.hasLabel('city') && !place.hasRelation('city')) {
    place.addRelation('city', place.noteId, true);
}