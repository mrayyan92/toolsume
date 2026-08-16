const dropArea = document.getElementById("dropArea");
const input = document.getElementById("image");
const preview = document.getElementById("preview");
const slider = document.getElementById("slider");
const value = document.getElementById("value");

// Open file picker when upload box is clicked
if (dropArea) {
    dropArea.onclick = () => input.click();
}

// Show image preview
if (input) {
    input.onchange = function () {
        showPreview(this.files[0]);
    };
}

// Drag events
if (dropArea) {

    dropArea.addEventListener("dragover", function(e){
        e.preventDefault();
        dropArea.classList.add("drag");
    });

    dropArea.addEventListener("dragleave", function(){
        dropArea.classList.remove("drag");
    });

    dropArea.addEventListener("drop", function(e){

        e.preventDefault();

        dropArea.classList.remove("drag");

        input.files = e.dataTransfer.files;

        showPreview(e.dataTransfer.files[0]);

    });

}

// Preview function
function showPreview(file){

    if(!file) return;

    if(preview.src && preview.src.startsWith("blob:")){
        URL.revokeObjectURL(preview.src);
    }

    preview.src = URL.createObjectURL(file);

    preview.style.display = "block";

}

// Slider
if(slider){

    slider.oninput = function(){

        value.innerHTML = this.value;

    }

}